import yaml
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode


def loadYamlConfig(file_path="config/config.yaml"):
    """
    Load a YAML configuration file and return its contents.

    :param file_path: Path to the YAML file.
    :return: Dictionary containing the YAML file contents.
    """

    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    
    return config


def GetBrowserConfig():
    """
    Get the browser configuration for web scraping.

    :return: A dictionary containing the browser configuration.
    """
    try:
        config = BrowserConfig(
            headless=True,
            # use_managed_browser=True,
            verbose=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            browser_type="chromium"
        )
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load browser configuration: {e}")
        return None
    
def GetCrawlerRunConfig():
    """
    Get the crawler run configuration for web scraping.

    :return: A CrawlerRunConfig object containing the crawler run configuration.
    """
    try:
        config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
            word_count_threshold=100,        # Minimum words per content block
            exclude_external_links=True,    # Remove external links
            remove_overlay_elements=True,   # Remove popups/modals
            process_iframes=True,
            exclude_external_images=True,
        exclude_social_media_domains=True,
        only_text=True,           # Only text content
        # verbose=False,
        )
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load crawler run configuration: {e}")
        return None
