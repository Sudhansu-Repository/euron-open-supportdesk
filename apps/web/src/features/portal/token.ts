/** The portal session token, per help center, in this browser only. */
const PREFIX = "supportdesk.portal.";

export function readPortalToken(slug: string): string | null {
  try {
    return localStorage.getItem(PREFIX + slug);
  } catch {
    return null;
  }
}

export function writePortalToken(slug: string, token: string | null) {
  try {
    if (token) localStorage.setItem(PREFIX + slug, token);
    else localStorage.removeItem(PREFIX + slug);
  } catch {
    // Storage blocked: the customer signs in again next time.
  }
}
