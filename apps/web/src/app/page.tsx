import { redirect } from "next/navigation";

/** The inbox is the front door; signed-out visitors are sent to sign in by the middleware. */
export default function Home() {
  redirect("/inbox");
}
