import pytest
import json
import os
from multi_site_analyzer import load_config


class TestConfig:
    
    def test_sites_config_exists(self):
        """Тест существования файла конфигурации"""
        assert os.path.exists('sites_config.json'), "Файл sites_config.json не найден"
    
    def test_sites_config_valid_json(self):
        """Тест валидности JSON в конфигурации"""
        try:
            config = load_config('sites_config.json')
            assert isinstance(config, dict), "Конфигурация должна быть словарем"
        except Exception as e:
            pytest.fail(f"Ошибка загрузки конфигурации: {e}")
    
    def test_sites_config_structure(self):
        """Тест структуры конфигурации"""
        config = load_config('sites_config.json')
        
        # Проверяем основные секции
        assert 'sites' in config, "Отсутствует секция 'sites'"
        assert 'default_settings' in config, "Отсутствует секция 'default_settings'"
        assert 'analysis_settings' in config, "Отсутствует секция 'analysis_settings'"
    
    def test_sites_section(self):
        """Тест секции сайтов"""
        config = load_config('sites_config.json')
        sites = config['sites']
        
        # Проверяем наличие всех трех сайтов
        expected_sites = ['piter-online', 'moskva-online', '101internet']
        for site_key in expected_sites:
            assert site_key in sites, f"Отсутствует сайт '{site_key}'"
        
        # Проверяем структуру каждого сайта
        for site_key, site_data in sites.items():
            required_fields = ['name', 'base_url', 'urls', 'description']
            for field in required_fields:
                assert field in site_data, f"Отсутствует поле '{field}' в сайте '{site_key}'"
            
            # Проверяем, что urls - это список
            assert isinstance(site_data['urls'], list), f"URLs для сайта '{site_key}' должны быть списком"
            assert len(site_data['urls']) > 0, f"Список URLs для сайта '{site_key}' пуст"
    
    def test_default_settings(self):
        """Тест настроек по умолчанию"""
        config = load_config('sites_config.json')
        settings = config['default_settings']
        
        required_fields = [
            'spreadsheet_id', 'sheet_name', 'upload_to_sheets', 
            'save_local', 'delay_between_requests', 'service_account_file'
        ]
        
        for field in required_fields:
            assert field in settings, f"Отсутствует настройка '{field}'"
    
    def test_analysis_settings(self):
        """Тест настроек анализа"""
        config = load_config('sites_config.json')
        analysis = config['analysis_settings']
        
        required_fields = [
            'check_headings', 'check_h1_h6', 'exclude_empty_headings',
            'compare_with_previous', 'save_comparison_data'
        ]
        
        for field in required_fields:
            assert field in analysis, f"Отсутствует настройка анализа '{field}'"
    
    def test_urls_validity(self):
        """Тест валидности URL в конфигурации"""
        config = load_config('sites_config.json')
        
        for site_key, site_data in config['sites'].items():
            for url in site_data['urls']:
                # Проверяем, что URL начинается с http/https
                assert url.startswith(('http://', 'https://')), f"Некорректный URL: {url}"
                
                # Проверяем, что URL не пустой
                assert len(url.strip()) > 0, f"Пустой URL в сайте '{site_key}'"
    
    def test_site_names_not_empty(self):
        """Тест, что названия сайтов не пустые"""
        config = load_config('sites_config.json')
        
        for site_key, site_data in config['sites'].items():
            assert len(site_data['name'].strip()) > 0, f"Пустое название сайта '{site_key}'"
    
    def test_base_urls_validity(self):
        """Тест валидности базовых URL"""
        config = load_config('sites_config.json')
        
        for site_key, site_data in config['sites'].items():
            base_url = site_data['base_url']
            assert base_url.startswith(('http://', 'https://')), f"Некорректный базовый URL для '{site_key}': {base_url}"
    
    def test_urls_count(self):
        """Тест количества URL для каждого сайта"""
        config = load_config('sites_config.json')
        
        for site_key, site_data in config['sites'].items():
            urls_count = len(site_data['urls'])
            print(f"Сайт '{site_key}': {urls_count} URL")
            assert urls_count > 0, f"Сайт '{site_key}' не содержит URL"
            assert urls_count >= 80, f"Сайт '{site_key}' содержит мало URL: {urls_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 