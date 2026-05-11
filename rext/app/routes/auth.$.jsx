import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";

async function notifyBackend(shop, accessToken, scopes) {
  const backendUrl = process.env.REXT_BACKEND_URL;
  const sharedSecret = process.env.REXT_BRIDGE_SHARED_SECRET;

  if (!backendUrl || !sharedSecret) return;

  try {
    await fetch(`${backendUrl}/api/v1/integrations/shopify/bridge/notify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Rext-Bridge-Secret": sharedSecret,
      },
      body: JSON.stringify({ shop, access_token: accessToken, scopes }),
    });
  } catch (err) {
    console.error("[bridge] Failed to notify backend:", err.message);
  }
}

export const loader = async ({ request }) => {
  const { session } = await authenticate.admin(request);

  if (session?.accessToken) {
    await notifyBackend(
      session.shop,
      session.accessToken,
      session.scope || "",
    );
  }

  return null;
};

export const headers = (headersArgs) => {
  return boundary.headers(headersArgs);
};
