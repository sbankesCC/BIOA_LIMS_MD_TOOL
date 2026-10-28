// Saves a downloaded file (a Blob from the API client) on the user's computer under the
// display file name the API gives, through a temporary link.

/** Save a Blob as a file with the given name. */
export function saveFile(blob: Blob, fileName: string): void {
  // A temporary object URL and link start the browser's download
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  // Clean up once the click has started the download
  link.remove();
  URL.revokeObjectURL(url);
}
