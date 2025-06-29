import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from multi_site_analyzer import MultiSiteAnalyzer, load_config


class TestMultiSiteAnalyzer:
    
    @pytest.fixture
    def sample_config(self):
        return {
            "sites": {
                "test-site": {
                    "name": "Test Site",
                    "base_url": "https://test.com",
                    "urls": ["https://test.com/page1", "https://test.com/page2"],
                    "description": "Test site"
                }
            },
            "default_settings": {
                "spreadsheet_id": "test_id",
                "sheet_name": "Test",
                "upload_to_sheets": False,
                "save_local": True,
                "delay_between_requests": 1
            }
        }
    
    @pytest.fixture
    def analyzer(self, sample_config):
        with patch('multi_site_analyzer.load_config', return_value=sample_config):
            return MultiSiteAnalyzer()
    
    def test_load_config(self, tmp_path):
        """Тест загрузки конфигурации"""
        config_data = {"test": "data"}
        config_file = tmp_path / "test_config.json"
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        
        result = load_config(str(config_file))
        assert result == config_data
    
    def test_analyzer_initialization(self, analyzer):
        """Тест инициализации анализатора"""
        assert analyzer.config is not None
        assert "sites" in analyzer.config
        assert "default_settings" in analyzer.config
    
    @patch('multi_site_analyzer.requests.get')
    def test_analyze_single_url(self, mock_get, analyzer):
        """Тест анализа одной URL"""
        # Мокаем HTML ответ
        mock_response = Mock()
        mock_response.text = """
        <html>
            <h1>Заголовок 1</h1>
            <h2>Заголовок 2</h2>
            <h3>Заголовок 3</h3>
            <p>Обычный текст</p>
        </html>
        """
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = analyzer.analyze_url("https://test.com")
        
        assert result['url'] == "https://test.com"
        assert result['status_code'] == 200
        assert result['h1_count'] == 1
        assert result['h2_count'] == 1
        assert result['h3_count'] == 1
        assert result['total_headings'] == 3
    
    @patch('multi_site_analyzer.requests.get')
    def test_analyze_url_with_error(self, mock_get, analyzer):
        """Тест анализа URL с ошибкой"""
        mock_get.side_effect = Exception("Connection error")
        
        result = analyzer.analyze_url("https://test.com")
        
        assert result['url'] == "https://test.com"
        assert result['error'] == "Connection error"
        assert result['status_code'] is None
    
    def test_get_site_urls(self, analyzer):
        """Тест получения URL сайта"""
        urls = analyzer.get_site_urls("test-site")
        assert len(urls) == 2
        assert "https://test.com/page1" in urls
        assert "https://test.com/page2" in urls
    
    def test_get_site_urls_invalid_site(self, analyzer):
        """Тест получения URL несуществующего сайта"""
        urls = analyzer.get_site_urls("non-existent")
        assert urls == []
    
    @patch('multi_site_analyzer.requests.get')
    def test_analyze_site(self, mock_get, analyzer):
        """Тест анализа всего сайта"""
        mock_response = Mock()
        mock_response.text = "<html><h1>Test</h1></html>"
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        results = analyzer.analyze_site("test-site")
        
        assert len(results) == 2
        for result in results:
            assert result['h1_count'] == 1
            assert result['status_code'] == 200
    
    def test_save_results(self, analyzer, tmp_path):
        """Тест сохранения результатов"""
        test_results = [
            {
                'url': 'https://test.com/page1',
                'h1_count': 1,
                'h2_count': 0,
                'status_code': 200
            }
        ]
        
        output_file = tmp_path / "test_results.json"
        analyzer.save_results(test_results, str(output_file))
        
        assert output_file.exists()
        
        with open(output_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        
        assert len(saved_data) == 1
        assert saved_data[0]['url'] == 'https://test.com/page1'


class TestConfigValidation:
    
    def test_valid_config_structure(self):
        """Тест валидной структуры конфигурации"""
        config = {
            "sites": {
                "site1": {
                    "name": "Site 1",
                    "base_url": "https://site1.com",
                    "urls": ["https://site1.com/page1"],
                    "description": "Test site"
                }
            },
            "default_settings": {
                "spreadsheet_id": "test_id",
                "sheet_name": "Test",
                "upload_to_sheets": False,
                "save_local": True,
                "delay_between_requests": 1
            }
        }
        
        # Проверяем, что конфигурация содержит необходимые ключи
        assert "sites" in config
        assert "default_settings" in config
        assert "site1" in config["sites"]
        assert "name" in config["sites"]["site1"]
        assert "urls" in config["sites"]["site1"]
    
    def test_missing_required_fields(self):
        """Тест отсутствующих обязательных полей"""
        config = {
            "sites": {
                "site1": {
                    "name": "Site 1"
                    # Отсутствуют base_url и urls
                }
            }
        }
        
        # Проверяем, что отсутствуют обязательные поля
        assert "base_url" not in config["sites"]["site1"]
        assert "urls" not in config["sites"]["site1"]


if __name__ == "__main__":
    pytest.main([__file__]) 