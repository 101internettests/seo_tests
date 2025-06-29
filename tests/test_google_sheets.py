import pytest
from unittest.mock import Mock, patch, MagicMock
from google_sheets_service_account import GoogleSheetsServiceAccount


class TestGoogleSheetsServiceAccount:
    
    @pytest.fixture
    def sheets_service(self):
        """Фикстура для создания экземпляра сервиса"""
        with patch('google_sheets_service_account.service_account.Credentials.from_service_account_file'):
            return GoogleSheetsServiceAccount('test_key.json')
    
    def test_initialization(self, sheets_service):
        """Тест инициализации сервиса"""
        assert sheets_service.service_account_file == 'test_key.json'
        assert sheets_service.service is not None
    
    @patch('google_sheets_service_account.service_account.Credentials.from_service_account_file')
    def test_initialization_with_credentials(self, mock_credentials):
        """Тест инициализации с учетными данными"""
        mock_creds = Mock()
        mock_credentials.return_value = mock_creds
        
        service = GoogleSheetsServiceAccount('test_key.json')
        
        mock_credentials.assert_called_once_with('test_key.json', scopes=[
            'https://www.googleapis.com/auth/spreadsheets'
        ])
    
    def test_read_data(self, sheets_service):
        """Тест чтения данных из таблицы"""
        # Мокаем ответ от Google Sheets API
        mock_response = {
            'values': [
                ['URL', 'H1', 'H2', 'H3', 'Total'],
                ['https://test.com', '1', '2', '3', '6']
            ]
        }
        
        sheets_service.service.spreadsheets().values().get().execute.return_value = mock_response
        
        result = sheets_service.read_data('test_spreadsheet_id', 'Test Sheet')
        
        assert result == mock_response['values']
        sheets_service.service.spreadsheets().values().get.assert_called_once_with(
            spreadsheetId='test_spreadsheet_id',
            range='Test Sheet'
        )
    
    def test_append_data(self, sheets_service):
        """Тест добавления данных в таблицу"""
        test_data = [
            ['https://test.com', '1', '2', '3', '6']
        ]
        
        sheets_service.service.spreadsheets().values().append().execute.return_value = {
            'updates': {'updatedRows': 1}
        }
        
        result = sheets_service.append_data('test_spreadsheet_id', 'Test Sheet', test_data)
        
        assert result['updates']['updatedRows'] == 1
        sheets_service.service.spreadsheets().values().append.assert_called_once_with(
            spreadsheetId='test_spreadsheet_id',
            range='Test Sheet',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body={'values': test_data}
        )
    
    def test_clear_data(self, sheets_service):
        """Тест очистки данных в таблице"""
        sheets_service.service.spreadsheets().values().clear().execute.return_value = {
            'clearedRange': 'Test Sheet!A1:E100'
        }
        
        result = sheets_service.clear_data('test_spreadsheet_id', 'Test Sheet')
        
        assert result['clearedRange'] == 'Test Sheet!A1:E100'
        sheets_service.service.spreadsheets().values().clear.assert_called_once_with(
            spreadsheetId='test_spreadsheet_id',
            range='Test Sheet'
        )
    
    def test_get_sheet_info(self, sheets_service):
        """Тест получения информации о листе"""
        mock_response = {
            'sheets': [
                {
                    'properties': {
                        'title': 'Test Sheet',
                        'sheetId': 123
                    }
                }
            ]
        }
        
        sheets_service.service.spreadsheets().get().execute.return_value = mock_response
        
        result = sheets_service.get_sheet_info('test_spreadsheet_id')
        
        assert result == mock_response['sheets']
        sheets_service.service.spreadsheets().get.assert_called_once_with(
            spreadsheetId='test_spreadsheet_id'
        )
    
    def test_format_results_for_sheets(self, sheets_service):
        """Тест форматирования результатов для Google Sheets"""
        test_results = [
            {
                'url': 'https://test.com/page1',
                'h1_count': 1,
                'h2_count': 2,
                'h3_count': 3,
                'h4_count': 0,
                'h5_count': 0,
                'h6_count': 0,
                'total_headings': 6,
                'status_code': 200,
                'site_name': 'Test Site',
                'site_key': 'test-site'
            }
        ]
        
        formatted_data = sheets_service.format_results_for_sheets(test_results)
        
        assert len(formatted_data) == 2  # Заголовок + данные
        assert formatted_data[0] == ['Дата', 'Сайт', 'URL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'Всего заголовков', 'Статус']
        assert formatted_data[1][2] == 'https://test.com/page1'  # URL
        assert formatted_data[1][3] == 1  # H1 count
        assert formatted_data[1][1] == 'Test Site'  # Site name
    
    def test_upload_results(self, sheets_service):
        """Тест загрузки результатов в таблицу"""
        test_results = [
            {
                'url': 'https://test.com/page1',
                'h1_count': 1,
                'h2_count': 2,
                'h3_count': 3,
                'h4_count': 0,
                'h5_count': 0,
                'h6_count': 0,
                'total_headings': 6,
                'status_code': 200,
                'site_name': 'Test Site',
                'site_key': 'test-site'
            }
        ]
        
        # Мокаем методы
        sheets_service.append_data = Mock(return_value={'updates': {'updatedRows': 1}})
        
        result = sheets_service.upload_results('test_spreadsheet_id', 'Test Sheet', test_results)
        
        assert result is True
        sheets_service.append_data.assert_called_once()
    
    def test_upload_results_empty(self, sheets_service):
        """Тест загрузки пустых результатов"""
        result = sheets_service.upload_results('test_spreadsheet_id', 'Test Sheet', [])
        
        assert result is False
    
    def test_error_handling_read_data(self, sheets_service):
        """Тест обработки ошибок при чтении данных"""
        sheets_service.service.spreadsheets().values().get().execute.side_effect = Exception("API Error")
        
        with pytest.raises(Exception):
            sheets_service.read_data('test_spreadsheet_id', 'Test Sheet')
    
    def test_error_handling_append_data(self, sheets_service):
        """Тест обработки ошибок при добавлении данных"""
        sheets_service.service.spreadsheets().values().append().execute.side_effect = Exception("API Error")
        
        with pytest.raises(Exception):
            sheets_service.append_data('test_spreadsheet_id', 'Test Sheet', [['test']])


if __name__ == "__main__":
    pytest.main([__file__]) 