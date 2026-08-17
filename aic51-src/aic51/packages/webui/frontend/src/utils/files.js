export function getBlob(blobData, mimeType) {
    if (typeof blobData === "string" && mimeType && mimeType.includes("csv")) {
        // Prepend UTF-8 BOM so Excel decodes Vietnamese characters (đ, ổ, ê...) correctly
        return new Blob(["\uFEFF" + blobData], { type: "text/csv;charset=utf-8;" });
    }
    return new Blob([blobData], { type: mimeType });
}

export function downloadFile(blob, name) {
  const tmpElement = document.createElement("a");
  tmpElement.href = URL.createObjectURL(blob);
  tmpElement.download = name;
  tmpElement.target = "_blank";
  tmpElement.click();
  tmpElement.remove();
}
