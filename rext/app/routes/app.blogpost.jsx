import { useEffect, useRef, useState } from "react";
import { Form, useActionData, useNavigation } from "react-router";
import { authenticate } from "../shopify.server";

export const action = async ({ request }) => {
  const { admin } = await authenticate.admin(request);

  const formData = await request.formData();
  const title = (formData.get("title") || "").toString().trim();
  const body = (formData.get("body") || "").toString();
  const featureImageUrl = (formData.get("featureImageUrl") || "")
    .toString()
    .trim();

  if (!title || !body) {
    return { error: "Title and content are required." };
  }

  if (/src\s*=\s*["'](?:data:image|blob:)/i.test(body)) {
    return {
      error:
        "Image source is temporary (blob/base64). Upload via image tool so Shopify CDN URLs are inserted.",
    };
  }

  if (
    featureImageUrl &&
    /^(?:data:image|blob:)/i.test(featureImageUrl)
  ) {
    return {
      error:
        "Feature image must be a hosted URL. Upload the feature image to Shopify Files first.",
    };
  }

  // Get first blog
  const blogQuery = await admin.graphql(`
    query {
      blogs(first: 1) {
        edges {
          node {
            id
          }
        }
      }
    }
  `);

  const blogData = await blogQuery.json();
  const blogId = blogData.data.blogs.edges[0]?.node?.id;

  if (!blogId) {
    return { error: "No blog found in your store. Please create a blog first." };
  }

  // Create article
  const response = await admin.graphql(`
    mutation articleCreate($article: ArticleCreateInput!) {
      articleCreate(article: $article) {
        article {
          id
          title
        }
        userErrors {
          field
          message
        }
      }
    }
  `,
  {
    variables: {
      article: {
        blogId,
        title,
        body,
        ...(featureImageUrl
          ? {
              image: {
                url: featureImageUrl,
                altText: title,
              },
            }
          : {}),
        isPublished: true,
        author: {
          name: "Store Owner",
        },
      },
    },
  });

  const result = await response.json();
  const article = result.data?.articleCreate?.article;
  const errors = result.data?.articleCreate?.userErrors;

  if (article) {
    return { success: true, article };
  }

  return { error: errors?.[0]?.message || "Failed to create blog post." };
};

export default function BlogPost() {
  const actionData = useActionData();
  const navigation = useNavigation();
  const isLoading = navigation.state === "submitting";

  const editorRef = useRef(null);
  const quillRef = useRef(null);
  const [bodyValue, setBodyValue] = useState("");
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [featureImageUrl, setFeatureImageUrl] = useState("");
  const [isUploadingFeatureImage, setIsUploadingFeatureImage] = useState(false);
  const [featureImageError, setFeatureImageError] = useState("");
  const formRef = useRef(null);
  const featureImageFileInputRef = useRef(null);

  const uploadImageFile = async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/app/api/upload-image", {
      method: "POST",
      body: formData,
    });

    const payload = await res.json();
    if (!res.ok || !payload?.url) {
      throw new Error(payload?.error || "Image upload failed.");
    }

    return payload.url;
  };

  const insertUploadedImage = async (file) => {
    if (!file || !file.type?.startsWith("image/")) {
      setUploadError("Please select a valid image file.");
      return;
    }

    setUploadError("");
    setIsUploadingImage(true);

    try {
      const imageUrl = await uploadImageFile(file);
      const quill = quillRef.current;
      const range = quill.getSelection(true) || { index: quill.getLength() };
      quill.insertEmbed(range.index, "image", imageUrl);
      quill.setSelection(range.index + 1);
      setBodyValue(quill.root.innerHTML);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Image upload failed.");
    } finally {
      setIsUploadingImage(false);
    }
  };

  const uploadFeatureImage = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setFeatureImageError("");
    setIsUploadingFeatureImage(true);

    try {
      const url = await uploadImageFile(file);
      setFeatureImageUrl(url);
    } catch (error) {
      setFeatureImageError(
        error instanceof Error ? error.message : "Feature image upload failed.",
      );
    } finally {
      setIsUploadingFeatureImage(false);
      event.target.value = "";
    }
  };

  useEffect(() => {
    // Dynamically import Quill to avoid SSR issues
    import("quill").then((QuillModule) => {
      const Quill = QuillModule.default;

      if (editorRef.current && !quillRef.current) {
        // Add Quill CSS
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "https://cdn.jsdelivr.net/npm/quill@2/dist/quill.snow.css";
        document.head.appendChild(link);

        quillRef.current = new Quill(editorRef.current, {
          theme: "snow",
          placeholder: "Write your blog post content here...",
          modules: {
            toolbar: {
              container: [
                [{ header: [1, 2, 3, false] }],
                ["bold", "italic", "underline"],
                [{ color: [] }],
                [{ align: [] }],
                ["link", "image"],
                ["clean"],
              ],
              handlers: {
                image: imageHandler,
              },
            },
          },
        });

        quillRef.current.on("text-change", () => {
          setBodyValue(quillRef.current.root.innerHTML);
        });

        quillRef.current.root.addEventListener("paste", (event) => {
          const pastedFile = event.clipboardData?.files?.[0];
          if (pastedFile && pastedFile.type?.startsWith("image/")) {
            event.preventDefault();
            void insertUploadedImage(pastedFile);
          }
        });

        quillRef.current.root.addEventListener("drop", (event) => {
          const droppedFile = event.dataTransfer?.files?.[0];
          if (droppedFile && droppedFile.type?.startsWith("image/")) {
            event.preventDefault();
            void insertUploadedImage(droppedFile);
          }
        });
      }
    });
  }, []);

  // Image handler — shows prompt for URL or file upload
  function imageHandler() {
    const quill = quillRef.current;

    // Create modal
    const modal = document.createElement("div");
    modal.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(0,0,0,0.5); z-index: 9999;
      display: flex; align-items: center; justify-content: center;
    `;

    modal.innerHTML = `
      <div style="background: white; padding: 24px; border-radius: 8px; width: 400px; font-family: sans-serif;">
        <h3 style="margin: 0 0 16px">Insert Image</h3>

        <p style="margin: 0 0 8px; font-size: 14px; font-weight: 600;">Paste Image URL</p>
        <input id="img-url-input" type="text" placeholder="https://example.com/image.jpg"
          style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; margin-bottom: 16px;" />

        <p style="margin: 0 0 8px; font-size: 14px; font-weight: 600;">Or Upload from Device</p>
        <input id="img-file-input" type="file" accept="image/*"
          style="margin-bottom: 16px;" />

        <div style="display: flex; gap: 8px; justify-content: flex-end;">
          <button id="img-cancel" style="padding: 8px 16px; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; background: white;">Cancel</button>
          <button id="img-insert" style="padding: 8px 16px; background: #008060; color: white; border: none; border-radius: 4px; cursor: pointer;">Insert</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Cancel
    modal.querySelector("#img-cancel").onclick = () => {
      document.body.removeChild(modal);
    };

    // Insert
    modal.querySelector("#img-insert").onclick = () => {
      const urlInput = modal.querySelector("#img-url-input").value.trim();
      const fileInput = modal.querySelector("#img-file-input").files[0];

      if (urlInput) {
        // Insert image from URL
        const range = quill.getSelection(true);
        quill.insertEmbed(range.index, "image", urlInput);
        document.body.removeChild(modal);
      } else if (fileInput) {
        void insertUploadedImage(fileInput).finally(() => {
          document.body.removeChild(modal);
        });
      } else {
        alert("Please enter an image URL or select a file.");
      }
    };
  }

  const handleSubmit = () => {
    // Sync latest editor HTML before submit.
    const hiddenInput = formRef.current.querySelector("#body-hidden");
    hiddenInput.value = quillRef.current?.root?.innerHTML || bodyValue;
  };

  // Clear editor on success
  useEffect(() => {
    if (actionData?.success && quillRef.current) {
      quillRef.current.setText("");
      setBodyValue("");
      setFeatureImageUrl("");
      setFeatureImageError("");
      setUploadError("");
      setIsUploadingImage(false);
      setIsUploadingFeatureImage(false);
      formRef.current.reset();
      if (featureImageFileInputRef.current) {
        featureImageFileInputRef.current.value = "";
      }
    }
  }, [actionData]);

  return (
    <s-page heading="Create Blog Post">
      <Form method="post" ref={formRef} onSubmit={handleSubmit}>
        <s-section heading="New Blog Post">

          {actionData?.success && (
            <p style={{ color: "green", marginTop: 0 }}>
              Blog post published successfully.
            </p>
          )}

          {actionData?.error && (
            <p style={{ color: "red", marginTop: 0 }}>{actionData.error}</p>
          )}

          <div style={{ display: "grid", gap: "16px", maxWidth: "720px" }}>

            <div>
              <label htmlFor="title" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>Title</label>
              <input
                id="title"
                name="title"
                type="text"
                placeholder="Enter blog post title"
                required
                style={{ width: "100%", padding: "8px", border: "1px solid #ccc", borderRadius: 4, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label htmlFor="featureImageUrl" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                Feature image URL
              </label>
              <input
                id="featureImageUrl"
                name="featureImageUrl"
                type="url"
                placeholder="https://cdn.shopify.com/..."
                value={featureImageUrl}
                onChange={(event) => setFeatureImageUrl(event.currentTarget.value)}
                style={{ width: "100%", padding: "8px", border: "1px solid #ccc", borderRadius: 4, boxSizing: "border-box" }}
              />
              <div style={{ marginTop: 8 }}>
                <label htmlFor="featureImageFile" style={{ display: "block", marginBottom: 4, fontSize: 12, color: "#666" }}>
                  Or upload feature image from device
                </label>
                <input
                  id="featureImageFile"
                  type="file"
                  accept="image/*"
                  ref={featureImageFileInputRef}
                  onChange={uploadFeatureImage}
                />
              </div>
              {isUploadingFeatureImage && (
                <p style={{ marginTop: 8, color: "#666", fontSize: 12 }}>
                  Uploading feature image...
                </p>
              )}
              {featureImageError && (
                <p style={{ marginTop: 8, color: "red", fontSize: 12 }}>
                  {featureImageError}
                </p>
              )}
              {featureImageUrl && (
                <img
                  src={featureImageUrl}
                  alt="Feature preview"
                  style={{ marginTop: 8, maxWidth: "280px", borderRadius: 6, border: "1px solid #ddd" }}
                />
              )}
            </div>

            <div>
              <label style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>Content</label>
              <div ref={editorRef} style={{ minHeight: "200px", background: "white" }} />
              <p style={{ marginTop: 8, color: "#666", fontSize: 12 }}>
                Images from device are uploaded to Shopify Files and inserted as CDN URLs.
              </p>
              {isUploadingImage && (
                <p style={{ marginTop: 8, color: "#666", fontSize: 12 }}>Uploading image...</p>
              )}
              {uploadError && (
                <p style={{ marginTop: 8, color: "red", fontSize: 12 }}>{uploadError}</p>
              )}
              {/* Hidden input to carry Quill HTML content */}
              <input type="hidden" id="body-hidden" name="body" />
            </div>

     <s-button
              type="submit"
              variant="primary"
              {...(isLoading ? { loading: true } : {})}
            >
              {isLoading ? "Publishing..." : "Publish Blog Post"}
            </s-button>

          </div>
        </s-section>
      </Form>
    </s-page>
  );
}