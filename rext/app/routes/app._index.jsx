import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }) => {
  const { admin, session } = await authenticate.admin(request);

  const response = await admin.graphql(`
    query {
      articles(first: 250) {
        edges {
          node {
            id
            title
            handle
            publishedAt
            blog {
              title
              handle
            }
          }
        }
      }
    }
  `);

  const data = await response.json();
  const articles = data?.data?.articles?.edges?.map((e) => e.node) || [];
  const shop = session.shop;

  const published = articles.filter((a) => a.publishedAt !== null).length;
  const draft = articles.length - published;

  const recent = articles.slice(0, 5).map((a) => ({
    ...a,
    storeUrl: `https://${shop}/blogs/${a.blog?.handle}/${a.handle}`,
  }));

  return { total: articles.length, published, draft, recent };
};

export default function Dashboard() {
  const { total, published, draft, recent } = useLoaderData();

  const cardStyle = {
    background: "white",
    border: "1px solid #e1e3e5",
    borderRadius: 8,
    padding: "20px 24px",
    minWidth: 140,
    flex: 1,
  };

  const labelStyle = { margin: 0, fontSize: 13, color: "#6d7175", fontWeight: 500 };
  const valueStyle = { margin: "8px 0 0", fontSize: 32, fontWeight: 700, color: "#202223" };

  return (
    <s-page heading="Dashboard">
      <s-section heading="Blog Post Overview">
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
          <div style={cardStyle}>
            <p style={labelStyle}>Total Posts</p>
            <p style={valueStyle}>{total}</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Published</p>
            <p style={{ ...valueStyle, color: "#008060" }}>{published}</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Draft</p>
            <p style={{ ...valueStyle, color: "#b98900" }}>{draft}</p>
          </div>
        </div>

        <h3 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 12px", color: "#202223" }}>
          Recent Posts
        </h3>

        {recent.length === 0 ? (
          <p style={{ color: "#6d7175", fontSize: 14 }}>No blog posts yet. Create your first one!</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #e1e3e5", textAlign: "left" }}>
                <th style={{ padding: "8px 12px", color: "#6d7175", fontWeight: 500 }}>Title</th>
                <th style={{ padding: "8px 12px", color: "#6d7175", fontWeight: 500 }}>Blog</th>
                <th style={{ padding: "8px 12px", color: "#6d7175", fontWeight: 500 }}>Status</th>
                <th style={{ padding: "8px 12px", color: "#6d7175", fontWeight: 500 }}>Published At</th>
                <th style={{ padding: "8px 12px", color: "#6d7175", fontWeight: 500 }}>Link</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((article) => (
                <tr key={article.id} style={{ borderBottom: "1px solid #f1f2f3" }}>
                  <td style={{ padding: "10px 12px", color: "#202223" }}>{article.title}</td>
                  <td style={{ padding: "10px 12px", color: "#6d7175" }}>{article.blog?.title || "—"}</td>
                  <td style={{ padding: "10px 12px" }}>
                    <span style={{
                      display: "inline-block",
                      padding: "2px 10px",
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: 600,
                      background: article.publishedAt ? "#e3f1ec" : "#fff3cd",
                      color: article.publishedAt ? "#008060" : "#b98900",
                    }}>
                      {article.publishedAt ? "Published" : "Draft"}
                    </span>
                  </td>
                  <td style={{ padding: "10px 12px", color: "#6d7175" }}>
                    {article.publishedAt
                      ? new Date(article.publishedAt).toLocaleDateString()
                      : "—"}
                  </td>
                  <td style={{ padding: "10px 12px" }}>
                    {article.publishedAt ? (
                      <a
                        href={article.storeUrl}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: "#008060", fontSize: 13, textDecoration: "none", fontWeight: 500 }}
                      >
                        View →
                      </a>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </s-section>
    </s-page>
  );
}

export const headers = (headersArgs) => {
  return boundary.headers(headersArgs);
};
