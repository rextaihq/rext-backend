import { authenticate } from "../shopify.server";

const jsonResponse = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });

export const loader = async () => {
  return jsonResponse({ error: "Method not allowed" }, 405);
};

export const action = async ({ request }) => {
  try {
    const { admin } = await authenticate.admin(request);
    const formData = await request.formData();
    const file = formData.get("file");

    const isFileLike =
      !!file &&
      typeof file === "object" &&
      typeof file.name === "string" &&
      typeof file.type === "string" &&
      typeof file.size === "number";

    if (!isFileLike) {
      return jsonResponse({ error: "No image file provided." }, 400);
    }

    if (!file.type.startsWith("image/")) {
      return jsonResponse({ error: "Only image files are supported." }, 400);
    }

    const stagedUploadMutation = `#graphql
      mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
        stagedUploadsCreate(input: $input) {
          stagedTargets {
            url
            resourceUrl
            parameters {
              name
              value
            }
          }
          userErrors {
            message
          }
        }
      }
    `;

    const stagedUploadRes = await admin.graphql(stagedUploadMutation, {
      variables: {
        input: [
          {
            filename: file.name,
            mimeType: file.type,
            resource: "IMAGE",
            httpMethod: "POST",
            fileSize: String(file.size),
          },
        ],
      },
    });

    const stagedUploadJson = await stagedUploadRes.json();
    const stagedErrors =
      stagedUploadJson.data?.stagedUploadsCreate?.userErrors || [];

    if (stagedErrors.length > 0) {
      return jsonResponse({ error: stagedErrors[0].message }, 400);
    }

    const stagedTarget =
      stagedUploadJson.data?.stagedUploadsCreate?.stagedTargets?.[0];

    if (!stagedTarget?.url || !stagedTarget?.resourceUrl) {
      return jsonResponse({ error: "Could not create staged upload." }, 500);
    }

    const uploadForm = new FormData();
    for (const param of stagedTarget.parameters || []) {
      uploadForm.append(param.name, param.value);
    }
    uploadForm.append("file", file, file.name);

    const uploadToStorageRes = await fetch(stagedTarget.url, {
      method: "POST",
      body: uploadForm,
    });

    if (!uploadToStorageRes.ok) {
      return jsonResponse({ error: "Uploading image to Shopify storage failed." }, 502);
    }

    const fileCreateMutation = `#graphql
      mutation fileCreate($files: [FileCreateInput!]!) {
        fileCreate(files: $files) {
          files {
            id
            ... on MediaImage {
              image {
                url
              }
            }
            ... on GenericFile {
              url
            }
          }
          userErrors {
            message
          }
        }
      }
    `;

    const fileCreateRes = await admin.graphql(fileCreateMutation, {
      variables: {
        files: [
          {
            alt: file.name,
            contentType: "IMAGE",
            originalSource: stagedTarget.resourceUrl,
          },
        ],
      },
    });

    const fileCreateJson = await fileCreateRes.json();
    const fileCreateErrors = fileCreateJson.data?.fileCreate?.userErrors || [];

    if (fileCreateErrors.length > 0) {
      return jsonResponse({ error: fileCreateErrors[0].message }, 400);
    }

    const createdFile = fileCreateJson.data?.fileCreate?.files?.[0];
    const immediateUrl = createdFile?.image?.url || createdFile?.url;

    if (immediateUrl) {
      return jsonResponse({ url: immediateUrl });
    }

    const fileId = createdFile?.id;

    if (!fileId) {
      return jsonResponse(
        {
          error:
            "Image uploaded but Shopify did not return a file id. Please try again.",
        },
        500,
      );
    }

    const nodeQuery = `#graphql
      query getFileNode($id: ID!) {
        node(id: $id) {
          ... on MediaImage {
            image {
              url
            }
          }
          ... on GenericFile {
            url
          }
        }
      }
    `;

    // Shopify files can be briefly unavailable while processing. Poll a few times.
    for (let i = 0; i < 8; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const nodeRes = await admin.graphql(nodeQuery, { variables: { id: fileId } });
      const nodeJson = await nodeRes.json();
      const readyUrl = nodeJson.data?.node?.image?.url || nodeJson.data?.node?.url;
      if (readyUrl) {
        return jsonResponse({ url: readyUrl });
      }
    }

    return jsonResponse(
      {
        error:
          "Image uploaded but is still processing. Please retry inserting the image in a few seconds.",
      },
      202,
    );
  } catch (error) {
    return jsonResponse(
      {
        error:
          error instanceof Error ? error.message : "Unexpected upload error.",
      },
      500,
    );
  }
};
