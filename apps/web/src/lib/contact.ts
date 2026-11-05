import { obj, str } from "./read";

/**
 * An address a visitor left in the widget's "email me" form. The API stores it as an
 * unverified contact (customer.attributes.contact_email), never as the customer's email.
 */
export function contactEmail(attributes: unknown): string | null {
  const v = str(obj(attributes).contact_email);
  return v && v.includes("@") ? v.trim() : null;
}
