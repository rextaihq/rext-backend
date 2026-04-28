import crypto from "node:crypto";
function json(data, init = {}) {
  return new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json", ...init.headers },
    status: init.status || 200,
    ...init
  });
}
import { unauthenticated } from "../shopify.server";

// Keep same value as backend SHOPIFY_BRIDGE_SHARED_SECRET
const BRIDGE_SECRET = process.env.REXT_BRIDGE_SHARED_SECRET || "";
const MAX_SKEW_SECONDS = 300;

function normalizeShop(value = "") {
  let v = String(value).trim().toLowerCase();
  v = v.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (v.endsWith(".myshopify.com")) return v;
  if (!v.includes(".")) return `${v}.myshopify.com`;
  return v;
}

function verifySignature(timestamp, rawBody, signature) {
  if (!BRIDGE_SECRET) return false;
  if (!timestamp || !signature) return false;

  const now = Math.floor(Date.now() / 1000);
  const ts = Number(timestamp);
  if (!Number.isFinite(ts) || Math.abs(now - ts) > MAX_SKEW_SECONDS) return false;

  const expected = crypto
    .createHmac("sha256", BRIDGE_SECRET)
    .update(`${timestamp}.${rawBody}`)
    .digest("hex");

  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(signature, "utf8");
  if (a.length !== b.length) return false;

  return crypto.timingSafeEqual(a, b);
}

export async function action({ request }) {
  if (request.method !== "POST") {
    return json({ error: "Method not allowed" }, { status: 405 });
  }

  const timestamp = request.headers.get("x-rext-timestamp");
  const signature = request.headers.get("x-rext-signature");

  const rawBody = await request.text();
  if (!verifySignature(timestamp, rawBody, signature)) {
    return json({ error: "Invalid signature" }, { status: 401 });
  }

  let payload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return json({ error: "Invalid JSON" }, { status: 400 });
  }

  const {
    storeUrl,
    storeHandle,
    title,
    body,
    published = true,
    tags = [],
    handle,
    featureImageUrl,
  } = payload || {};

  if (!title || !body) {
    return json({ error: "title and body are required" }, { status: 400 });
  }

  const shopDomain = normalizeShop(storeUrl || storeHandle || "");
  if (!shopDomain.endsWith(".myshopify.com")) {
    return json({ error: "Invalid store domain" }, { status: 422 });
  }

  let admin;
  try {
    const context = await unauthenticated.admin(shopDomain);
    admin = context.admin;
  } catch (err) {
    return json(
      { error: `No offline session found for shop ${shopDomain}. Reinstall app first.` },
      { status: 401 },
    );
  }

  // 1) find blog
  const blogResp = await admin.graphql(`
    query {
      blogs(first: 1) {
        edges { node { id } }
      }
    }
  `);

  const blogRespJson = await blogResp.json();
  const blogId = blogRespJson?.data?.blogs?.edges?.[0]?.node?.id;
  if (!blogId) {
    return json({ error: "No blog found in store" }, { status: 422 });
  }

  // 2) create article
  const articleResp = await admin.graphql(`
    mutation ArticleCreate($article: ArticleCreateInput!) {
      articleCreate(article: $article) {
        article {
          id
          title
          handle
          publishedAt
        }
        userErrors {
          field
          message
        }
      }
    }
  `, {
    variables: {
      article: {
        blogId,
        title,
        body,
        author: { name: "Rext App" },
        isPublished: !!published,
        ...(handle ? { handle } : {}),
        ...(Array.isArray(tags) && tags.length ? { tags } : {}),
        ...(featureImageUrl
          ? { image: { url: featureImageUrl, altText: title } }
          : {}),
      },
    },
  });

  const articleRespJson = await articleResp.json();
  const data = articleRespJson?.data?.articleCreate;
  
  const userErrors = data?.userErrors || [];
  if (userErrors.length) {
    return json({ error: userErrors[0].message }, { status: 422 });
  }

  const article = data?.article;
  return json({
    article: {
      id: article?.id || null,
      title: article?.title || title,
      url: article?.onlineStoreUrl || null,
      publishedAt: article?.publishedAt || null,
      handle: article?.handle || null,
    },
  });
}