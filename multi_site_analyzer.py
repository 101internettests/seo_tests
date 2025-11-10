#!/usr/bin/env python3
"""
Мультисайтовый SEO анализатор для всех сайтов
"""

import os
import sys
import argparse
import logging
import json
import requests
import time
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from google_sheets_service_account import GoogleSheetsServiceAccount
from telegram_bot import TelegramBot

# Логирование будет настроено в main()

logger = logging.getLogger(__name__)


# Подсказки для распознавания страниц защиты и типичных страниц ошибок
_PROTECTION_HINTS = [
    'just a moment',
    'ddos protection',
    'cloudflare',
    'captcha',
    'please enable cookies'
]

_ERROR_PAGE_HINTS = [
    '404',
    'not found',
    'ошибка',
    'server error',
    'page not found',
    'access denied',
    'forbidden',
    'bad gateway',
    'service unavailable'
]


class SEOParser:
    """Простой SEO парсер для анализа заголовков"""
    
    def __init__(self, delay_between_requests: float = 2.0, config: Dict[str, Any] = None, sheets_manager=None, max_retries: int = 2, backoff_seconds: float = 0.7, ignore_protection: bool = False, use_cloudscraper: bool = False):
        self.delay_between_requests = delay_between_requests
        # Инициализируем HTTP-сессию
        if use_cloudscraper:
            try:
                import cloudscraper  # type: ignore
                self.session = cloudscraper.create_scraper()
                logger.info("Инициализирован cloudscraper для HTTP-сессии")
            except Exception as e:
                logger.warning(f"Не удалось инициализировать cloudscraper, используем requests.Session(): {e}")
                self.session = requests.Session()
        else:
            self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.config = config
        self.sheets_manager = sheets_manager
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.ignore_protection = ignore_protection
    
    def analyze_page(self, url: str) -> Dict[str, Any]:
        """
        Анализ одной страницы
        
        Args:
            url: URL страницы для анализа
            
        Returns:
            Результат анализа
        """
        result = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'status': 'error',
            'error': None,
            'headings': {},
            'comparison': {}
        }
        
        try:
            last_error = None

            for attempt in range(self.max_retries + 1):
                try:
                    # Используем requests.get, чтобы удобнее было мокать в тестах
                    response = self.session.get(
                        url,
                        headers=self.session.headers,
                        timeout=30
                    )

                    # Повторяем при временных серверных ошибках
                    if 500 <= response.status_code < 600:
                        raise requests.exceptions.HTTPError(f"Server error {response.status_code}")

                    text_lower = (response.text or '').lower()
                    if (not self.ignore_protection) and any(hint in text_lower for hint in _PROTECTION_HINTS):
                        raise RuntimeError("Temporary protection or captcha page detected")

                    # Парсим HTML
                    soup = BeautifulSoup(response.content, 'html.parser')

                    # Анализируем заголовки
                    headings = self._analyze_headings(soup)

                    result.update({
                        'status': 'success',
                        'status_code': response.status_code,
                        'headings': headings,
                        'comparison': self._compare_with_previous(url, headings)
                    })

                    # Задержка между запросами после успешного запроса
                    if self.delay_between_requests > 0:
                        time.sleep(self.delay_between_requests)

                    last_error = None
                    break

                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError, RuntimeError) as e:
                    last_error = e
                    if attempt < self.max_retries:
                        time.sleep(self.backoff_seconds * (2 ** attempt))
                        continue
                    else:
                        raise

        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Ошибка анализа {url}: {e}")
        
        return result

    def _analyze_headings(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Анализ заголовков, title и description на странице"""
        headings = {}

        # Анализ заголовков H1-H6
        for i in range(1, 7):
            tag = f'h{i}'
            elements = soup.find_all(tag)

            total_count = len(elements)
            non_empty_count = len([el for el in elements if el.get_text(strip=True)])

            headings[f'{tag}_total'] = total_count
            headings[f'{tag}_non_empty'] = non_empty_count

        # Общее количество заголовков
        headings['total_headings'] = sum(headings[f'h{i}_non_empty'] for i in range(1, 7))

        # Подсчет title тегов с контентом (исключая типичные страницы ошибок, но не любое слово "error")
        title_tags = soup.find_all('title')
        title_count = 0
        for title in title_tags:
            title_text = (title.get_text(strip=True) or '')
            title_text_lower = title_text.lower()
            is_typical_error = any(hint in title_text_lower for hint in _ERROR_PAGE_HINTS)
            if title_text and not is_typical_error:
                title_count += 1
        
        headings['title_count'] = title_count
        headings['title_result'] = f"Title with content: {title_count}"

        # Подсчет meta description тегов с контентом (исключая типичные страницы ошибок)
        meta_descriptions = soup.find_all('meta', attrs={'name': 'description'})
        description_count = 0
        for meta in meta_descriptions:
            content = (meta.get('content', '') or '').strip()
            content_lower = content.lower()
            is_typical_error = any(hint in content_lower for hint in _ERROR_PAGE_HINTS)
            if content and not is_typical_error:
                description_count += 1
        
        headings['description_count'] = description_count
        headings['description_result'] = f"Description with content: {description_count}"

        return headings
    
    def _compare_with_previous(self, url: str, current_headings: Dict[str, int]) -> Dict[str, Any]:
        """Сравнение с предыдущими результатами из Google Sheets"""
        if not self.config:
            return {
                'status': 'no_config',
                'changes': {},
                'errors': ['Конфигурация не передана в парсер']
            }
            
        try:
            # Получаем настройки из конфигурации
            settings = self.config['default_settings']
            spreadsheet_id = settings.get('spreadsheet_id')
            sheet_name = settings.get('sheet_name', 'Лист1')
            
            if not spreadsheet_id:
                return {
                    'status': 'no_spreadsheet_id',
                    'changes': {},
                    'errors': ['Не указан ID таблицы в конфигурации']
                }
            
            # Используем переданный sheets_manager
            if not self.sheets_manager:
                return {
                    'status': 'no_sheets_manager',
                    'changes': {},
                    'errors': ['GoogleSheetsServiceAccount не инициализирован']
                }
            
            # Получаем все данные из таблицы
            range_name = f'{sheet_name}!A:T'
            try:
                existing_data = self.sheets_manager.get_sheet_data(spreadsheet_id, range_name)
            except Exception as e:
                logger.warning(f"Не удалось получить данные из Google Sheets: {e}")
                return {
                    'status': 'sheets_error',
                    'changes': {},
                    'errors': [f'Ошибка чтения из Google Sheets: {e}']
                }
            
            if not existing_data or len(existing_data) <= 1:  # Только заголовки или пусто
                return {
                    'status': 'no_previous_data',
                    'changes': {},
                    'errors': []
                }
            
            # Строим карту названий столбцов -> индекс
            headers = existing_data[0]
            header_to_index = {str(h).strip().lower(): idx for idx, h in enumerate(headers)}

            def find_idx(candidates):
                for name in candidates:
                    key = str(name).strip().lower()
                    if key in header_to_index:
                        return header_to_index[key]
                return None

            url_idx = find_idx(['url'])

            # Ищем последние данные для этого URL
            previous_data = None
            if url_idx is not None:
                for row in reversed(existing_data[1:]):  # Пропускаем заголовки, идем с конца
                    if len(row) > url_idx and row[url_idx] == url:
                        previous_data = row
                        break
            else:
                # Fallback: прежняя логика со вторым столбцом
                for row in reversed(existing_data[1:]):
                    if len(row) >= 2 and row[1] == url:
                        previous_data = row
                        break
            
            if not previous_data:
                logger.info(f"Предыдущих данных для {url} не найдено - это первая проверка")
                return {
                    'status': 'no_previous_data',
                    'changes': {},
                    'errors': []
                }

            # Извлекаем данные о заголовках из предыдущего результата
            # Предпочитаем поиск по названиям колонок; при отсутствии — мягкий fallback на индексы
            try:
                changes = {}
                # Непустые заголовки
                for i in range(1, 7):
                    non_empty_idx = find_idx([f'H{i} (непустые)', f'h{i}_непустые', f'h{i}_non_empty'])
                    if non_empty_idx is not None and len(previous_data) > non_empty_idx:
                        try:
                            prev_value = int(str(previous_data[non_empty_idx]).strip())
                        except (ValueError, TypeError):
                            prev_value = 0
                    else:
                        # fallback по индексам: 3..8 (0-баз)
                        idx = 2 + i
                        try:
                            prev_value = int(previous_data[idx]) if len(previous_data) > idx else 0
                        except (ValueError, TypeError):
                            prev_value = 0

                    current_value = current_headings.get(f'h{i}_non_empty', 0)
                    diff = current_value - prev_value
                    if diff != 0:
                        changes[f'h{i}_non_empty'] = {
                            'difference': diff,
                            'previous': prev_value,
                            'current': current_value
                        }

                # Общие заголовки
                for i in range(1, 7):
                    total_idx = find_idx([f'H{i} (всего)', f'h{i}_всего', f'h{i}_total'])
                    if total_idx is not None and len(previous_data) > total_idx:
                        try:
                            prev_value = int(str(previous_data[total_idx]).strip())
                        except (ValueError, TypeError):
                            prev_value = 0
                    else:
                        # fallback по индексам: 10..15 (0-баз) — соответствуют h1..h6 total
                        idx = 8 + i
                        try:
                            prev_value = int(previous_data[idx]) if len(previous_data) > idx else 0
                        except (ValueError, TypeError):
                            prev_value = 0

                    current_value = current_headings.get(f'h{i}_total', 0)
                    diff = current_value - prev_value
                    if diff != 0:
                        changes[f'h{i}_total'] = {
                            'difference': diff,
                            'previous': prev_value,
                            'current': current_value
                        }

                # Title count
                title_idx = find_idx(['title count', 'title_count'])
                prev_title_count = 0
                if title_idx is not None and len(previous_data) > title_idx:
                    try:
                        raw = previous_data[title_idx]
                        if raw and str(raw).strip():
                            prev_title_count = int(str(raw).strip())
                    except (ValueError, TypeError):
                        prev_title_count = 0
                elif len(previous_data) > 15:
                    # fallback прежний столбец 16 (0-баз 15)
                    try:
                        raw = previous_data[15]
                        if raw and str(raw).strip():
                            prev_title_count = int(str(raw).strip())
                    except (ValueError, TypeError):
                        prev_title_count = 0

                current_title_count = current_headings.get('title_count', 0)
                if prev_title_count != current_title_count:
                    changes['title_count'] = {
                        'difference': current_title_count - prev_title_count,
                        'previous': prev_title_count,
                        'current': current_title_count
                    }

                # Description count
                description_idx = find_idx(['description count', 'description_count'])
                prev_description_count = 0
                if description_idx is not None and len(previous_data) > description_idx:
                    try:
                        raw = previous_data[description_idx]
                        if raw and str(raw).strip():
                            prev_description_count = int(str(raw).strip())
                    except (ValueError, TypeError):
                        prev_description_count = 0
                elif len(previous_data) > 16:
                    # fallback прежний столбец 17 (0-баз 16)
                    try:
                        raw = previous_data[16]
                        if raw and str(raw).strip():
                            prev_description_count = int(str(raw).strip())
                    except (ValueError, TypeError):
                        prev_description_count = 0

                current_description_count = current_headings.get('description_count', 0)
                if prev_description_count != current_description_count:
                    changes['description_count'] = {
                        'difference': current_description_count - prev_description_count,
                        'previous': prev_description_count,
                        'current': current_description_count
                    }

                if changes:
                    return {
                        'status': 'changes_detected',
                        'changes': changes,
                        'errors': []
                    }
                else:
                    return {
                        'status': 'no_changes',
                        'changes': {},
                        'errors': []
                    }
                    
            except (ValueError, IndexError) as e:
                return {
                    'status': 'parsing_error',
                    'changes': {},
                    'errors': [f'Ошибка парсинга предыдущих данных: {e}']
                }
                
        except Exception as e:
            logger.error(f"Ошибка сравнения с предыдущими данными: {e}")
            return {
                'status': 'comparison_error',
                'changes': {},
                'errors': [f'Ошибка сравнения: {e}']
            }


class MultiSiteAnalyzer:
    def __init__(self, sites_config_file: str = 'sites_config.json', delay_between_requests: float = 2.0, max_retries: int = 2, backoff_seconds: float = 0.7, ignore_protection: bool = False, use_cloudscraper: bool = False):
        """
        Инициализация мультисайтового анализатора
        
        Args:
            sites_config_file: Путь к файлу конфигурации сайтов
            delay_between_requests: Задержка между запросами
            max_retries: Количество повторных попыток при временных ошибках
            backoff_seconds: Начальная задержка для экспоненциального бэкоффа
            ignore_protection: Игнорировать защитные страницы (капча/Cloudflare)
            use_cloudscraper: Использовать cloudscraper для обхода простых проверок
        """
        self.sites_config_file = sites_config_file
        self.config = self.load_sites_config()
        self.sheets_manager = GoogleSheetsServiceAccount()
        
        # Инициализируем Telegram бота
        self.telegram_bot = TelegramBot()
        if self.telegram_bot.bot_token and self.telegram_bot.chat_id:
            logger.info("Telegram бот инициализирован")
        else:
            logger.warning("Telegram бот не настроен (отсутствуют BOT_TOKEN или CHAT_ID)")
        
        # Создаем парсер с конфигурацией и sheets_manager
        self.parser = SEOParser(
            delay_between_requests=delay_between_requests,
            config=self.config,
            sheets_manager=self.sheets_manager,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            ignore_protection=ignore_protection,
            use_cloudscraper=use_cloudscraper
        )
        
    def load_sites_config(self) -> Dict:
        """Загрузка конфигурации сайтов"""
        if not os.path.exists(self.sites_config_file):
            raise FileNotFoundError(f"Файл конфигурации {self.sites_config_file} не найден")
        
        try:
            with open(self.sites_config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Конфигурация сайтов загружена из {self.sites_config_file}")
            return config
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            raise
    
    def get_site_urls(self, site_key: str = None) -> List[str]:
        """
        Получение URL для анализа
        
        Args:
            site_key: Ключ сайта (если None, возвращает все URL)
            
        Returns:
            Список URL для анализа
        """
        if site_key:
            if site_key not in self.config['sites']:
                # Для тестов возвращаем пустой список, а не исключение
                return []
            return self.config['sites'][site_key]['urls']
        else:
            # Возвращаем все URL всех сайтов
            all_urls = []
            for site_key, site_data in self.config['sites'].items():
                all_urls.extend(site_data['urls'])
            return all_urls
    
    def get_site_info(self, url: str) -> Dict:
        """
        Получение информации о сайте по URL
        
        Args:
            url: URL страницы
            
        Returns:
            Информация о сайте
        """
        for site_key, site_data in self.config['sites'].items():
            if any(url.startswith(site_url) for site_url in site_data['urls']):
                return {
                    'key': site_key,
                    'name': site_data['name'],
                    'base_url': site_data['base_url'],
                    'description': site_data['description']
                }
        return {'key': 'unknown', 'name': 'Неизвестный сайт', 'base_url': '', 'description': ''}
    
    def run_analysis(self, site_key: str = None, custom_urls: List[str] = None) -> Dict[str, List[Dict]]:
        """
        Запуск анализа для сайтов
        
        Args:
            site_key: Ключ конкретного сайта (если None, анализирует все)
            custom_urls: Пользовательские URL (переопределяет конфигурацию)
            
        Returns:
            Словарь с результатами по сайтам
        """
        # Определяем URL для анализа
        if custom_urls:
            urls_to_analyze = custom_urls
            logger.info(f"Анализируем пользовательские URL: {len(custom_urls)}")
        elif site_key:
            urls_to_analyze = self.get_site_urls(site_key)
            logger.info(f"Анализируем сайт '{site_key}': {len(urls_to_analyze)} URL")
        else:
            urls_to_analyze = self.get_site_urls()
            logger.info(f"Анализируем все сайты: {len(urls_to_analyze)} URL")
        
        # Группируем URL по сайтам
        sites_results = {}
        
        for url in urls_to_analyze:
            site_info = self.get_site_info(url)
            site_key = site_info['key']
            
            if site_key not in sites_results:
                sites_results[site_key] = {
                    'site_info': site_info,
                    'results': []
                }
            
            # Анализируем страницу
            try:
                result = self.parser.analyze_page(url)
                sites_results[site_key]['results'].append(result)
                logger.info(f"Проанализирована страница: {url}")
            except Exception as e:
                logger.error(f"Ошибка анализа {url}: {e}")
                sites_results[site_key]['results'].append({
                    'url': url,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'error',
                    'error': str(e)
                })
        
        return sites_results
    
    def print_results(self, sites_results: Dict[str, List[Dict]]):
        """Вывод результатов анализа"""
        print("\n" + "="*100)
        print("РЕЗУЛЬТАТЫ МУЛЬТИСАЙТОВОГО SEO АНАЛИЗА")
        print("="*100)
        
        total_sites = len(sites_results)
        total_pages = sum(len(site_data['results']) for site_data in sites_results.values())
        successful_pages = 0
        
        for site_key, site_data in sites_results.items():
            site_info = site_data['site_info']
            results = site_data['results']
            
            print(f"\n🌐 САЙТ: {site_info['name']} ({site_key})")
            print(f"   Описание: {site_info['description']}")
            print(f"   Базовый URL: {site_info['base_url']}")
            print(f"   Страниц проанализировано: {len(results)}")
            print("-" * 80)
            
            site_successful = 0
            
            for i, result in enumerate(results, 1):
                print(f"\n   {i}. {result['url']}")
                print(f"      Статус: {result['status']}")
                
                if result['status'] == 'success':
                    site_successful += 1
                    successful_pages += 1
                    
                    headings = result['headings']
                    print("      📈 Количество заголовков:")
                    
                    for j in range(1, 7):
                        tag = f'h{j}'
                        total = headings.get(f'{tag}_total', 0)
                        non_empty = headings.get(f'{tag}_non_empty', 0)
                        
                        if total > 0:
                            print(f"        {tag.upper()}: {non_empty} (всего: {total})")

                    # Показываем информацию о Title и Description
                    title_count = headings.get('title_count', 0)
                    title_result = headings.get('title_result', '')
                    description_count = headings.get('description_count', 0)
                    description_result = headings.get('description_result', '')

                    print("      📝 Title и Description:")
                    print(f"        Title: {title_result}")
                    print(f"        Description: {description_result}")
                    
                    # Проверяем сравнение
                    if 'comparison' in result:
                        comparison = result['comparison']
                        print(f"      🔍 Сравнение: {comparison['status']}")
                        
                        if comparison.get('errors'):
                            print("      ❌ Ошибки:")
                            for error in comparison['errors']:
                                print(f"        - {error}")
                        
                        if comparison.get('changes'):
                            print("      ✅ Изменения:")
                            for change_type, change_data in comparison['changes'].items():
                                print(f"        - {change_type}: +{change_data['difference']}")
                else:
                    print(f"      ❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            
            print(f"\n   📊 Статистика сайта: {site_successful}/{len(results)} успешно")
        
        print("\n" + "="*100)
        print(f"📈 ОБЩАЯ СТАТИСТИКА:")
        print(f"   🌐 Сайтов: {total_sites}")
        print(f"   📄 Страниц: {total_pages}")
        print(f"   ✅ Успешно: {successful_pages}")
        print(f"   ❌ Ошибок: {total_pages - successful_pages}")
        print(f"   📊 Процент успеха: {(successful_pages/total_pages*100):.1f}%" if total_pages > 0 else "   📊 Процент успеха: 0%")
        print("="*100)
    
    def save_results_locally(self, sites_results: Dict[str, List[Dict]]):
        """Сохранение результатов в локальный файл"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'multi_site_results_{timestamp}.json'
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(sites_results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Результаты сохранены в {filename}")
            print(f"💾 Результаты сохранены в {filename}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения результатов: {e}")
    
    def upload_to_sheets(self, sites_results: Dict[str, List[Dict]]):
        """Загрузка результатов в Google Sheets"""
        try:
            settings = self.config['default_settings']
            spreadsheet_id = settings.get('spreadsheet_id')
            sheet_name = settings.get('sheet_name', 'Лист1')
            service_account_file = settings.get('service_account_file', 'service-account-key.json')
            
            if not spreadsheet_id:
                logger.error("Не указан ID таблицы в конфигурации")
                return
            
            # Обновляем файл Service Account в менеджере
            self.sheets_manager.service_account_file = service_account_file
            
            # Подготавливаем все результаты для загрузки (без информации о сайтах)
            all_results = []
            for site_key, site_data in sites_results.items():
                all_results.extend(site_data['results'])
            
            logger.info(f"Загружаем результаты в Google Sheets: {spreadsheet_id}")
            
            success = self.sheets_manager.upload_results(
                spreadsheet_id, all_results, sheet_name
            )
            
            if success:
                logger.info("Результаты успешно загружены в Google Sheets")
                print("✅ Результаты успешно загружены в Google Sheets")
            else:
                logger.error("Ошибка загрузки результатов в Google Sheets")
                print("❌ Ошибка загрузки результатов в Google Sheets")
                
        except Exception as e:
            logger.error(f"Ошибка загрузки в Google Sheets: {e}")
            print(f"❌ Ошибка загрузки в Google Sheets: {e}")
    
    def send_telegram_report(self, sites_results: Dict[str, List[Dict]]):
        """Отправка отчета в Telegram"""
        try:
            if not self.telegram_bot.bot_token or not self.telegram_bot.chat_id:
                logger.warning("Telegram бот не настроен, пропускаем отправку отчета")
                return

            # Отправляем основную статистику
            success = self.telegram_bot.send_statistics(sites_results)
            if success:
                logger.info("Основная статистика отправлена в Telegram")
                print("📱 Основная статистика отправлена в Telegram")
            else:
                logger.error("Ошибка отправки основной статистики в Telegram")
                print("❌ Ошибка отправки основной статистики в Telegram")

            # Отправляем детальные изменения, если они есть
            changes_success = self.telegram_bot.send_detailed_changes(sites_results)
            if changes_success:
                logger.info("Детальные изменения отправлены в Telegram")
                print("📱 Детальные изменения отправлены в Telegram")
            else:
                logger.info("Детальные изменения не отправлены (нет изменений или ошибка)")

        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            print(f"❌ Ошибка отправки в Telegram: {e}")
    
    def send_telegram_error(self, error_message: str):
        """Отправка уведомления об ошибке в Telegram"""
        try:
            if not self.telegram_bot.bot_token or not self.telegram_bot.chat_id:
                return
            
            self.telegram_bot.send_error_notification(error_message)
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об ошибке в Telegram: {e}")
    
    def list_available_sites(self):
        """Вывод списка доступных сайтов"""
        print("\n📋 ДОСТУПНЫЕ САЙТЫ:")
        print("="*60)
        
        for site_key, site_data in self.config['sites'].items():
            print(f"\n🌐 {site_data['name']} ({site_key})")
            print(f"   Описание: {site_data['description']}")
            print(f"   Базовый URL: {site_data['base_url']}")
            print(f"   Страниц для анализа: {len(site_data['urls'])}")
            print("   URL:")
            for url in site_data['urls']:
                print(f"     - {url}")

    def analyze_url(self, url: str) -> dict:
        """Анализ одной страницы (для тестов)"""
        result = self.parser.analyze_page(url)
        # Приводим результат к формату, ожидаемому тестами
        headings = result.get('headings', {})
        return {
            'url': result.get('url'),
            'status_code': result.get('status_code'),
            'h1_count': headings.get('h1_non_empty', 0),
            'h2_count': headings.get('h2_non_empty', 0),
            'h3_count': headings.get('h3_non_empty', 0),
            'total_headings': headings.get('total_headings', 0),
            'title_count': headings.get('title_count', 0),
            'title_result': headings.get('title_result', ''),
            'description_count': headings.get('description_count', 0),
            'description_result': headings.get('description_result', ''),
            'error': result.get('error'),
        }

    def analyze_site(self, site_key: str) -> list:
        """Анализ всех страниц сайта (для тестов)"""
        urls = self.get_site_urls(site_key)
        results = []
        for url in urls:
            results.append(self.analyze_url(url))
        return results

    def save_results(self, results: list, filename: str):
        """Сохраняет результаты анализа в файл (для тестов)"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


def load_config(config_file: str) -> Dict[str, Any]:
    """Загрузка конфигурации из файла"""
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Файл конфигурации {config_file} не найден")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        raise Exception(f"Ошибка загрузки конфигурации: {e}")


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(description='Мультисайтовый SEO анализатор')
    parser.add_argument('--config', '-c', default='sites_config.json', 
                       help='Путь к файлу конфигурации сайтов')
    parser.add_argument('--site', '-s', 
                       help='Анализировать конкретный сайт (piter-online, moskva-online, 101internet)')
    parser.add_argument('--list-sites', action='store_true',
                       help='Показать список доступных сайтов')
    parser.add_argument('--urls', nargs='+',
                       help='Пользовательские URL для анализа')
    parser.add_argument('--no-sheets', action='store_true',
                       help='Не загружать результаты в Google Sheets')
    parser.add_argument('--no-local', action='store_true',
                       help='Не сохранять результаты локально')
    parser.add_argument('--no-telegram', action='store_true',
                       help='Не отправлять отчет в Telegram')
    parser.add_argument('--no-log', action='store_true',
                       help='Не записывать логи в файл')
    parser.add_argument('--delay', type=float, default=2.0,
                       help='Задержка между запросами, сек (по умолчанию 2.0)')
    parser.add_argument('--max-retries', type=int, default=2,
                       help='Число повторов при временных ошибках (по умолчанию 2)')
    parser.add_argument('--backoff', type=float, default=0.7,
                       help='Начальная задержка для экспоненциального бэкоффа, сек (по умолчанию 0.7)')
    parser.add_argument('--ignore-protection', action='store_true',
                       help='Игнорировать защитные страницы (капча/Cloudflare)')
    parser.add_argument('--use-cloudscraper', action='store_true',
                       help='Использовать cloudscraper для обхода простых проверок')
    
    args = parser.parse_args()
    
    # Настройка логирования
    if args.no_log:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('multi_site_analyzer.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Создаем анализатор
        analyzer = MultiSiteAnalyzer(
            sites_config_file=args.config,
            delay_between_requests=args.delay,
            max_retries=args.max_retries,
            backoff_seconds=args.backoff,
            ignore_protection=args.ignore_protection,
            use_cloudscraper=args.use_cloudscraper
        )
        
        # Показываем список сайтов
        if args.list_sites:
            analyzer.list_available_sites()
            return
        
        # Запускаем анализ
        results = analyzer.run_analysis(
            site_key=args.site,
            custom_urls=args.urls
        )
        
        # Выводим результаты
        analyzer.print_results(results)
        
        # Сохраняем результаты локально
        if not args.no_local:
            analyzer.save_results_locally(results)
        
        # Загружаем результаты в Google Sheets
        if not args.no_sheets:
            analyzer.upload_to_sheets(results)
        
        # Отправляем отчет в Telegram
        if not args.no_telegram:
            analyzer.send_telegram_report(results)
        
        print(f"\n🎉 Анализ завершен успешно!")
            
    except KeyboardInterrupt:
        print("\n⏹️ Анализ прерван пользователем")
        try:
            if 'analyzer' in locals() and getattr(analyzer, 'telegram_bot', None):
                analyzer.send_telegram_error("Анализ прерван пользователем")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        print(f"❌ Критическая ошибка: {e}")
        try:
            if 'analyzer' in locals() and getattr(analyzer, 'telegram_bot', None):
                analyzer.send_telegram_error(f"Критическая ошибка: {e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
