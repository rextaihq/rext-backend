from src.flow.engines.agent.content_agent import create_content_agent
import asyncio
import os

agent = asyncio.run(create_content_agent(debug=True))