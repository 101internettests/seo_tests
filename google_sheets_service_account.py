import os
import json
import logging
from typing import List, Any, Dict
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Попытка загрузить .env файл (только для Telegram)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен

logger = logging.getLogger(__name__)

# Области доступа для Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


class GoogleSheetsServiceAccount:
    """Класс для работы с Google Sheets API через Service Account"""
    
    def __init__(self, service_account_file: str = 'service-account-key.json', spreadsheet_id: str = '', sheet_name: str = ''):
        """
        Инициализация Google Sheets API с Service Account
        """
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        
        try:
            # Проверяем существование файла
            # if not os.path.exists(service_account_file):
            #     raise FileNotFoundError(f"Файл {service_account_file} не найден")
            #
            # # Загружаем и проверяем формат файла
            # with open(service_account_file, 'r', encoding='utf-8') as f:
            #     service_account_info = json.load(f)
            #
            # # Проверяем, что это Service Account Key, а не OAuth Client ID
            # if 'type' not in service_account_info or service_account_info['type'] != 'service_account':
            #     raise ValueError(
            #         "Неверный формат файла! У вас OAuth 2.0 Client ID, а нужен Service Account Key.\n"
            #         "Создайте Service Account в Google Cloud Console:\n"
            #         "1. APIs & Services → Credentials\n"
            #         "2. Create Credentials → Service Account\n"
            #         "3. Add Key → Create new key → JSON"
            #     )
            #
            # # Проверяем обязательные поля
            # required_fields = ['client_email', 'token_uri', 'private_key']
            # missing_fields = [field for field in required_fields if field not in service_account_info]
            #
            # if missing_fields:
            #     raise ValueError(f"В файле Service Account отсутствуют обязательные поля: {', '.join(missing_fields)}")
            #
            # Создаем credentials
            service_account_info = {
                "type": os.getenv("TYPE"),
                "project_id": os.getenv("PROJECT_ID"),
                "client_email": os.getenv("CLIENT_EMAIL"),
                "token_uri": os.getenv("TOKEN_URI"),
                "private_key": os.getenv("PRIVATE_KEY"),
                "private_key_id": os.getenv("PRIVATE_KEY_ID"),
                "client_id": os.getenv("CLIENT_ID"),
                "auth_uri": os.getenv("AUTH_URI"),
                "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
                "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
                "universe_domain": os.getenv("UNIVERSE_DOMAIN"),
            }
            print(service_account_info)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )

            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info(f"Google Sheets API инициализирован успешно")
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла {service_account_file}: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets API: {e}")
            raise
    
    def get_sheet_data(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        """
        Получение данных из Google таблицы
        
        Args:
            spreadsheet_id: ID таблицы
            range_name: Диапазон ячеек (например, 'A1:Z1000')
            
        Returns:
            Список строк с данными
        """
        if not self.service:
            self.authenticate()
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name).execute()
            values = result.get('values', [])
            logger.info(f"Получено {len(values)} строк из таблицы")
            return values
        except HttpError as error:
            logger.error(f"Ошибка получения данных: {error}")
            return []
    
    def update_sheet(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]):
        """
        Обновление данных в Google таблице
        
        Args:
            spreadsheet_id: ID таблицы
            range_name: Диапазон ячеек
            values: Данные для записи
        """
        if not self.service:
            self.authenticate()
        
        try:
            body = {
                'values': values
            }
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id, range=range_name,
                valueInputOption='RAW', body=body).execute()
            logger.info(f"Обновлено {result.get('updatedCells')} ячеек")
            return result
        except HttpError as error:
            logger.error(f"Ошибка обновления данных: {error}")
            return None
    
    def append_data(self, spreadsheet_id: str, range_name: str, values: List[List[Any]]):
        """
        Добавление данных в конец Google таблицы
        
        Args:
            spreadsheet_id: ID таблицы
            range_name: Диапазон ячеек (например, 'A:Z')
            values: Данные для добавления
        """
        if not self.service:
            self.authenticate()
        
        try:
            body = {
                'values': values
            }
            result = self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id, range=range_name,
                valueInputOption='RAW', insertDataOption='INSERT_ROWS', body=body).execute()
            logger.info(f"Добавлено {len(values)} строк")
            return result
        except HttpError as error:
            logger.error(f"Ошибка добавления данных: {error}")
            return None
    
    def format_results_for_sheet(self, results: List[Dict]) -> List[List[Any]]:
        """
        Форматирование результатов анализа для записи в таблицу
        
        Args:
            results: Результаты анализа от парсера
            
        Returns:
            Список строк для записи в таблицу
        """
        # Заголовки столбцов (старый простой формат)
        headers = [
            'Дата и время',
            'URL',
            'Статус',
            'H1 (непустые)',
            'H2 (непустые)',
            'H3 (непустые)',
            'H4 (непустые)',
            'H5 (непустые)',
            'H6 (непустые)',
            'H1 (всего)',
            'H2 (всего)',
            'H3 (всего)',
            'H4 (всего)',
            'H5 (всего)',
            'H6 (всего)',
            'Title count',
            'Description count',
            'Сравнение статус',
            'Ошибки',
            'Изменения'
        ]
        
        rows = [headers]
        
        for result in results:
            row = []
            
            # Дата и время
            timestamp = result.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    row.append(dt.strftime('%Y-%m-%d %H:%M:%S'))
                except:
                    row.append(timestamp)
            else:
                row.append('')
            
            # URL
            row.append(result.get('url', ''))
            
            # Статус
            row.append(result.get('status', ''))
            
            # Количество непустых заголовков
            headings = result.get('headings', {})
            for i in range(1, 7):
                row.append(headings.get(f'h{i}_non_empty', 0))
            
            # Общее количество заголовков
            for i in range(1, 7):
                row.append(headings.get(f'h{i}_total', 0))
            
            # Title и Description count
            row.append(headings.get('title_count', 0))
            row.append(headings.get('description_count', 0))
            
            # Статус сравнения
            comparison = result.get('comparison', {})
            row.append(comparison.get('status', ''))
            
            # Ошибки
            errors = comparison.get('errors', [])
            row.append('; '.join(errors) if errors else '')
            
            # Изменения
            changes = comparison.get('changes', {})
            changes_str = []
            if isinstance(changes, dict):
                for change_type, change_data in changes.items():
                    if isinstance(change_data, dict) and 'difference' in change_data:
                        changes_str.append(f"{change_type}: +{change_data['difference']}")
                    else:
                        changes_str.append(f"{change_type}: {change_data}")
            elif isinstance(changes, list):
                changes_str = [str(change) for change in changes]
            else:
                changes_str = [str(changes)] if changes else []
            row.append('; '.join(changes_str) if changes_str else '')
            
            rows.append(row)
        
        return rows
    
    def upload_results(self, spreadsheet_id: str, results: List[Dict], sheet_name: str = 'Лист1'):
        """
        Загрузка результатов анализа в Google таблицу
        
        Args:
            spreadsheet_id: ID таблицы
            results: Результаты анализа
            sheet_name: Название листа
        """
        try:
            # Форматируем данные для таблицы
            formatted_data = self.format_results_for_sheet(results)
            
            # Определяем диапазон для записи (20 столбцов: A-T)
            range_name = f'{sheet_name}!A:T'
            
            # Добавляем данные в конец таблицы
            result = self.append_data(spreadsheet_id, range_name, formatted_data)
            
            if result:
                logger.info(f"Результаты успешно загружены в таблицу {spreadsheet_id}")
                return True
            else:
                logger.error("Ошибка загрузки результатов в таблицу")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка загрузки результатов: {e}")
            return False


def create_service_account_instructions():
    """Создание инструкций по настройке Service Account"""
    instructions = {
        "title": "Настройка Service Account для Google Sheets API",
        "steps": [
            "1. Перейдите в Google Cloud Console (https://console.cloud.google.com/)",
            "2. Выберите ваш проект",
            "3. Перейдите в 'APIs & Services' > 'Credentials'",
            "4. Нажмите 'Create Credentials' > 'Service Account'",
            "5. Заполните форму:",
            "   - Service account name: 'seo-parser'",
            "   - Service account ID: автоматически заполнится",
            "   - Description: 'Service account for SEO parser'",
            "6. Нажмите 'Create and Continue'",
            "7. На следующем экране нажмите 'Continue' (роли не нужны)",
            "8. Нажмите 'Done'",
            "9. Найдите созданный Service Account в списке и нажмите на него",
            "10. Перейдите на вкладку 'Keys'",
            "11. Нажмите 'Add Key' > 'Create new key'",
            "12. Выберите 'JSON' и нажмите 'Create'",
            "13. Скачайте файл и переименуйте в 'service-account-key.json'",
            "14. Поместите файл в корень проекта",
            "15. Добавьте email из Service Account в права доступа к таблице"
        ],
        "note": "Service Account не требует проверки Google и работает сразу"
    }
    
    with open('service_account_instructions.json', 'w', encoding='utf-8') as f:
        json.dump(instructions, f, ensure_ascii=False, indent=2)
    
    print("Создан файл service_account_instructions.json с инструкциями")


if __name__ == "__main__":
    create_service_account_instructions() 