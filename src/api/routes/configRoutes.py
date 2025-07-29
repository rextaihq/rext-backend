from fastapi import APIRouter, HTTPException
from src.api.schema.configSchema import WorkflowConfigSchema
import yaml

router = APIRouter(
    prefix="/config",
    tags=["config"]
)

# ✅ Instantiate the LangGraph workflow once at startup
CONFIG_PATH = "config/config.yaml"

@router.get("/status")
def get_config_status():
    return {"status": "Config is active"}


# set the workflow configuration
@router.post("/configure")
def configure_workflow(config_data: WorkflowConfigSchema):
    """
    Configure the workflow with user-defined parameters.
    Saves the configuration as a YAML file.
    """
    config = {
        "GNews": {
            "url": "https://gnews.io/api/v4/top-headlines",
            "category": config_data.category or "technology",
            "country": config_data.country or "pk",
            "language": config_data.language or "en"
        },
        "rss_sources": {}
    }

    if config_data.rss_sources:
        for feed in config_data.rss_sources:
            config["rss_sources"][feed.title] = str(feed.url)

    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f)

    return {
        "message": "✅ Workflow configured and saved successfully.",
        "config": config
    }
