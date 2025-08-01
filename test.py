# (content-automation) mobeen@mobeen:~/Applications/Revnix/Automation/content-automation$ docker compose config
# name: content-automation
# services:
#   langgraph-api:
#     depends_on:
#       langgraph-postgres:
#         condition: service_healthy
#         required: true
#       langgraph-redis:
#         condition: service_healthy
#         required: true
#     environment:
#       DATABASE_URI: postgresql://sami:12345@langgraph-postgres:5432/langgraph_db
#       GNEWS_API_KEY: e135b8574311c5c84aad0386b9aca3fc
#       LANGSMITH_API_KEY: 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
#       OPENAI_API_KEY: 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
#       REDIS_URI: redis://langgraph-redis:6379
#       WP_TOKEN: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjEsIm5hbWUiOiJzdGFnaW5nX3dwYWVnaXMiLCJpYXQiOjE3NTMyNzk2MzEsImV4cCI6MTkxMDk1OTYzMX0.OWcNYsPd_C4xw_L6qBTdxe8m_W4mWAeD3lzwNFccLr4
#       WP_URL: https://staging.wpaegis.com/wp-json/wp/v2/posts
#     image: test
#     networks:
#       default: null
#     ports:
#       - mode: ingress
#         target: 8000
#         published: "8123"
#         protocol: tcp
#   langgraph-postgres:
#     environment:
#       POSTGRES_DB: langgraph_db
#       POSTGRES_PASSWORD: "12345"
#       POSTGRES_USER: sami
#     healthcheck:
#       test:
#         - CMD-SHELL
#         - pg_isready -U sami
#       timeout: 1s
#       interval: 5s
#       retries: 5
#       start_period: 10s
#     image: postgres:16
#     networks:
#       default: null
#     ports:
#       - mode: ingress
#         target: 5432
#         published: "5433"
#         protocol: tcp
#     volumes:
#       - type: volume
#         source: langgraph-data
#         target: /var/lib/postgresql/data
#         volume: {}
#   langgraph-redis:
#     healthcheck:
#       test:
#         - CMD-SHELL
#         - redis-cli ping
#       timeout: 1s
#       interval: 5s
#       retries: 5
#     image: redis:6
#     networks:
#       default: null
# networks:
#   default:
#     name: content-automation_default
# volumes:
#   langgraph-data:
#     name: content-automation_langgraph-data
#     driver: local
# (content-automation) mobeen@mobeen:~/Applications/Revnix/Automation/content-automation$ 