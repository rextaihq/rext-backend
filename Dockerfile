FROM langchain/langgraph-api:0.12.6-py3.11-wolfi

ENV MIGRATE_ON_START=true
ENV UV_NO_BUILD_ISOLATION=1
RUN uv pip install --system --no-cache-dir --extra-index-url https://pypi.org/simple "hatchling>=1.26.0" editables
RUN apk add --no-cache libnspr libnss dbus-libs glib libatk-1.0 libatk-bridge-2.0 at-spi2-core pango cairo fontconfig freetype harfbuzz ca-certificates curl bash alsa-lib libx11 libxcomposite libxdamage libxfixes libxrandr libxrender libxtst libxcursor libxi libsm libice libxkbcommon mesa-gles mesa-gbm cups-libs
COPY pyproject.toml uv.lock /tmp/rext-lock/
RUN cd /tmp/rext-lock && uv export --frozen --no-dev --no-emit-project --no-hashes --quiet -o requirements.txt && uv pip install --system --no-cache-dir -c /api/constraints.txt -r requirements.txt && rm -rf /tmp/rext-lock
RUN python -m nltk.downloader -d /usr/share/nltk_data punkt punkt_tab stopwords && python -c "from nltk.corpus import stopwords; from nltk.tokenize import word_tokenize; stopwords.words('english'); word_tokenize('ok')"
RUN playwright install chromium --only-shell && rm -rf /root/.cache/ms-playwright/chromium-1243 /root/.cache/ms-playwright/ffmpeg-1011
RUN crawl4ai-setup
RUN crawl4ai-doctor

# -- Adding local package . --
ADD . /deps/rext-backend
# -- End of local package . --

# -- Installing all local dependencies --
RUN for dep in /deps/*; do             echo "Installing $dep";             if [ -d "$dep" ]; then                 echo "Installing $dep";                 (cd "$dep" && PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir -c /api/constraints.txt -e .);             fi;         done
# -- End of local dependencies install --
ENV LANGGRAPH_STORE='{"path": "src/flow/store/rext_store.py:generate_store"}'
ENV LANGGRAPH_AUTH='{"path": "/deps/rext-backend/src/api/security/auth.py:auth", "disable_studio_auth": true}'
ENV LANGGRAPH_HTTP='{"app": "/deps/rext-backend/src/api/server.py:app", "cors": {"allow_origins": []}}'
ENV LANGGRAPH_CHECKPOINTER='{"ttl": {"default_ttl": 259200, "sweep_interval_minutes": 30}}'
ENV LANGSERVE_GRAPHS='{"agent": "main:graph"}'



# -- Ensure user deps didn't inadvertently overwrite langgraph-api
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api
# -- End of ensuring user deps didn't inadvertently overwrite langgraph-api --
# -- Removing build deps from the final image ~<:===~~~ --
RUN pip uninstall -y pip setuptools wheel
RUN rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* && find /usr/local/bin -name "pip*" -delete || true
RUN rm -rf /usr/lib/python*/site-packages/pip* /usr/lib/python*/site-packages/setuptools* /usr/lib/python*/site-packages/wheel* && find /usr/bin -name "pip*" -delete || true
RUN uv pip uninstall --system pip setuptools wheel && rm /usr/bin/uv /usr/bin/uvx

WORKDIR /deps/rext-backend