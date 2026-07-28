/** Trigger a browser "Save as" for bytes already fetched with an auth header.
 *
 *  Artifacts are streamed by the API behind a bearer token, so a plain navigation
 *  (`window.open`) cannot reach them -- navigation sends no Authorization header.
 *  The object URL is revoked on the next tick, once the click has been dispatched.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
