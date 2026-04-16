import os
import requests
import logging
import html
from typing import Dict, Any
from datetime import datetime
import time

# Попытка загрузить .env файл
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен

logger = logging.getLogger(__name__)

class TelegramBot:
    """Класс для работы с Telegram ботом"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        """
        Инициализация Telegram бота
        
        Args:
            bot_token: Токен бота (если не указан, берется из переменной окружения BOT_TOKEN)
            chat_id: ID чата (если не указан, берется из переменной окружения CHAT_ID)
        """
        self.bot_token = bot_token or os.getenv('BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('CHAT_ID')
        self.use_telegram_proxy = self._env_bool('USE_TELEGRAM_PROXY', False)
        self.telegram_proxy_url = (os.getenv('TELEGRAM_PROXY_URL') or '').strip()
        self.telegram_proxy_auth_secret = (os.getenv('TELEGRAM_PROXY_AUTH_SECRET') or '').strip()
        self.telegram_proxy_creds = (os.getenv('TELEGRAM_PROXY_CREDS') or '').strip()
        try:
            self.telegram_proxy_timeout_sec = float(os.getenv('TELEGRAM_PROXY_TIMEOUT_SEC', '15'))
        except Exception:
            self.telegram_proxy_timeout_sec = 15.0

        # Временная защита от дублей ошибок (по сообщению, в пределах окна времени)
        self._last_error_fingerprint = None
        self._last_error_ts = 0.0
        self._proxy_missing_env_logged = False

        if self.use_telegram_proxy:
            missing_proxy_env = self._missing_proxy_env()
            if missing_proxy_env:
                logger.warning(
                    "USE_TELEGRAM_PROXY=true, но отсутствуют обязательные env: %s",
                    ', '.join(missing_proxy_env),
                )
            else:
                logger.info("Telegram proxy режим включен")
        else:
            if not self.bot_token:
                logger.warning("BOT_TOKEN не найден в переменных окружения")
            if not self.chat_id:
                logger.warning("CHAT_ID не найден в переменных окружения")

    @staticmethod
    def _env_bool(name: str, default: bool = False) -> bool:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() in ('1', 'true', 'yes', 'y', 'on')

    def _missing_proxy_env(self):
        missing = []
        if not self.telegram_proxy_url:
            missing.append('TELEGRAM_PROXY_URL')
        if not self.telegram_proxy_auth_secret:
            missing.append('TELEGRAM_PROXY_AUTH_SECRET')
        if not self.telegram_proxy_creds:
            missing.append('TELEGRAM_PROXY_CREDS')
        return missing

    def is_configured(self) -> bool:
        """Проверка готовности транспорта уведомлений."""
        if self.use_telegram_proxy:
            return len(self._missing_proxy_env()) == 0
        return bool(self.bot_token and self.chat_id)
    
    def send_message(self, message: str) -> bool:
        """
        Отправка сообщения в Telegram
        
        Args:
            message: Текст сообщения
            
        Returns:
            True если сообщение отправлено успешно, False в противном случае
        """
        try:
            if self.use_telegram_proxy:
                missing_proxy_env = self._missing_proxy_env()
                if missing_proxy_env:
                    if not self._proxy_missing_env_logged:
                        logger.error(
                            "Telegram proxy missing required env vars: %s",
                            ', '.join(missing_proxy_env),
                        )
                        self._proxy_missing_env_logged = True
                    return False

                response = requests.post(
                    self.telegram_proxy_url,
                    headers={
                        'Content-Type': 'application/json',
                        'X-Authentication': self.telegram_proxy_auth_secret,
                    },
                    json={
                        'title': html.escape('SEO analyzer alert'),
                        'text': html.escape(message),
                        'creds': self.telegram_proxy_creds,
                        'parse_mode': 'HTML',
                        'disable_notification': False,
                    },
                    timeout=self.telegram_proxy_timeout_sec,
                )

                if response.status_code >= 400:
                    logger.error(
                        "Telegram proxy error: status=%s body=%s",
                        response.status_code,
                        (response.text or '')[:180],
                    )
                    return False

                logger.info("Сообщение успешно отправлено в Telegram через proxy")
                return True

            if not self.bot_token or not self.chat_id:
                logger.error("BOT_TOKEN или CHAT_ID не настроены")
                return False

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'  # Поддержка HTML разметки
            }

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()

            result = response.json()
            if result.get('ok'):
                logger.info("Сообщение успешно отправлено в Telegram")
                return True

            logger.error(f"Ошибка отправки в Telegram: {result.get('description', 'Неизвестная ошибка')}")
            return False
                
        except requests.exceptions.Timeout:
            if self.use_telegram_proxy:
                logger.error("Telegram proxy timeout after %ss", self.telegram_proxy_timeout_sec)
            else:
                logger.error("Таймаут сети при отправке в Telegram")
            return False
        except requests.exceptions.RequestException as e:
            if self.use_telegram_proxy:
                logger.error(f"Telegram proxy transport error: {e}")
            else:
                logger.error(f"Ошибка сети при отправке в Telegram: {e}")
            return False
        except Exception as e:
            if self.use_telegram_proxy:
                logger.error(f"Telegram proxy unexpected error: {e}")
            else:
                logger.error(f"Ошибка отправки в Telegram: {e}")
            return False

    def send_statistics(self, sites_results: Dict[str, Any]) -> bool:
        """
        Отправка статистики анализа в Telegram

        Args:
            sites_results: Результаты анализа сайтов

        Returns:
            True если сообщение отправлено успешно, False в противном случае
        """
        try:
            # Подсчитываем статистику
            total_sites = len(sites_results)
            total_pages = sum(len(site_data['results']) for site_data in sites_results.values())
            successful_pages = 0

            # Подсчитываем успешные страницы
            for site_data in sites_results.values():
                for result in site_data['results']:
                    if result.get('status') == 'success':
                        successful_pages += 1

            # Вычисляем процент успеха
            success_percentage = (successful_pages / total_pages * 100) if total_pages > 0 else 0

            # Подсчитываем статистику по SEO элементам
            pages_with_title = 0
            pages_with_description = 0
            total_title_count = 0
            total_description_count = 0

            for site_data in sites_results.values():
                for result in site_data['results']:
                    if result.get('status') == 'success' and 'headings' in result:
                        headings = result['headings']
                        title_count = headings.get('title_count', 0)
                        description_count = headings.get('description_count', 0)
                        
                        if title_count > 0:
                            pages_with_title += 1
                            total_title_count += title_count
                        if description_count > 0:
                            pages_with_description += 1
                            total_description_count += description_count

            # Формируем сообщение
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            message = f"""
<b>📊 ОТЧЕТ ОБ АНАЛИЗЕ SEO</b>
<i>{timestamp}</i>

<b>📈 ОБЩАЯ СТАТИСТИКА:</b>
🌐 Сайтов: {total_sites}
📄 Страниц: {total_pages}
✅ Успешно: {successful_pages}
❌ Ошибок: {total_pages - successful_pages}
📊 Процент успеха: {success_percentage:.1f}%

<b>🔍 SEO ЭЛЕМЕНТЫ:</b>
📝 Title: {pages_with_title}/{successful_pages} ({(pages_with_title/successful_pages*100) if successful_pages > 0 else 0:.1f}%)
📄 Description: {pages_with_description}/{successful_pages} ({(pages_with_description/successful_pages*100) if successful_pages > 0 else 0:.1f}%)

<b>🌐 ДЕТАЛИ ПО САЙТАМ:</b>"""

            # Добавляем информацию по каждому сайту (ограничиваем количество)
            site_count = 0
            for site_key, site_data in sites_results.items():
                if site_count >= 5:  # Ограничиваем до 5 сайтов в основном сообщении
                    break
                    
                site_info = site_data['site_info']
                results = site_data['results']
                
                site_successful = sum(1 for r in results if r.get('status') == 'success')
                site_success_percentage = (site_successful / len(results) * 100) if results else 0
                
                message += f"""

<b>{site_info['name']}</b> ({site_key})
📄 Страниц: {len(results)}
✅ Успешно: {site_successful}
❌ Ошибок: {len(results) - site_successful}
📊 Успех: {site_success_percentage:.1f}%"""
                
                site_count += 1
            
            if len(sites_results) > 5:
                message += f"""

... и еще {len(sites_results) - 5} сайтов"""
            
            # Добавляем краткую информацию об изменениях
            changes_count = 0
            for site_data in sites_results.values():
                for result in site_data['results']:
                    if result.get('status') == 'success' and 'comparison' in result:
                        comparison = result['comparison']
                        if comparison.get('status') == 'changes_detected':
                            changes_count += 1
            
            if changes_count > 0:
                message += f"""

<b>🔄 ИЗМЕНЕНИЯ:</b>
📈 Страниц с изменениями: {changes_count}"""
            
            message += f"""
<i> 💥 Ссылка на отчет: https://docs.google.com/spreadsheets/d/1NTyI48H4woktkCqnvjGsMOWZbnqs8oCMMNP3j_AJDkw/edit?gid=1041857980#gid=1041857980 </i>"
<i>🤖 Отправлено автоматически</i>"""
            
            # Отправляем основное сообщение (детальные изменения отправляет вызывающая сторона)
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Ошибка формирования статистики для Telegram: {e}")
            return False

    def send_error_notification(self, error_message: str) -> bool:
        """
        Отправка уведомления об ошибке

        Args:
            error_message: Сообщение об ошибке

        Returns:
            True если сообщение отправлено успешно, False в противном случае
        """
        # Дедупликация: не отправляем одинаковое сообщение чаще, чем раз в 60 секунд
        try:
            normalized = ' '.join((error_message or '').split())
            now_ts = time.time()
            if self._last_error_fingerprint == normalized and (now_ts - self._last_error_ts) < 60:
                logger.info("Пропускаем дублирующее уведомление об ошибке (менее 60с)")
                return True
        except Exception:
            # В случае любой ошибки в дедупликации просто продолжаем обычную отправку
            pass

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = f"""
<b>⚠️ ОШИБКА АНАЛИЗА</b>
<i>{timestamp}</i>

{error_message}

<i>🤖 Отправлено автоматически</i>"""
        success = self.send_message(message)
        if success:
            try:
                self._last_error_fingerprint = ' '.join((error_message or '').split())
                self._last_error_ts = time.time()
            except Exception:
                pass
        return success

    def send_detailed_changes(self, sites_results: Dict[str, Any]) -> bool:
        """
        Отправка детальных изменений в Telegram

        Args:
            sites_results: Результаты анализа сайтов

        Returns:
            True если сообщение отправлено успешно, False в противном случае
        """
        try:
            # Собираем все изменения
            changes_details = []
            
            for site_data in sites_results.values():
                for result in site_data['results']:
                    if result.get('status') == 'success' and 'comparison' in result:
                        comparison = result['comparison']
                        if comparison.get('status') == 'changes_detected':
                            url = result.get('url', 'Неизвестная ссылка')
                            changes = comparison.get('changes', {})
                            
                            # Формируем детали изменений для этой страницы
                            page_changes = []
                            for change_type, change_data in changes.items():
                                if isinstance(change_data, dict) and 'difference' in change_data:
                                    diff = change_data['difference']
                                    if diff > 0:
                                        page_changes.append(f"➕ {change_type}: +{diff}")
                                    elif diff < 0:
                                        page_changes.append(f"➖ {change_type}: {diff}")
                                elif isinstance(change_data, dict) and change_data.get('type') == 'content_change':
                                    page_changes.append(f"🔄 {change_type}: изменено содержимое")
                            
                            if page_changes:
                                changes_details.append(f"🔗 {url}\n" + "\n".join(f"   {change}" for change in page_changes))
            
            if not changes_details:
                return True  # Нет изменений для отправки
            
            # Формируем сообщение с деталями
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            message = f"""
<b>🔄 ДЕТАЛЬНЫЕ ИЗМЕНЕНИЯ</b>
<i>{timestamp}</i>

"""
            
            # Добавляем изменения, разбивая на части если нужно
            current_message = message
            for detail in changes_details:
                # Проверяем, не превышает ли сообщение лимит Telegram (4096 символов)
                if len(current_message + detail) > 4000:  # Оставляем запас
                    # Отправляем текущее сообщение
                    self.send_message(current_message + "\n<i>🤖 Отправлено автоматически</i>")
                    # Начинаем новое сообщение
                    current_message = f"""
<b>🔄 ДЕТАЛЬНЫЕ ИЗМЕНЕНИЯ (продолжение)</b>
<i>{timestamp}</i>

{detail}"""
                else:
                    current_message += f"\n{detail}"
            
            # Отправляем последнее сообщение
            if current_message != message:
                return self.send_message(current_message + "\n<i>🤖 Отправлено автоматически</i>")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отправки детальных изменений в Telegram: {e}")
            return False
