import { redirect } from "next/navigation";

/** Landing: the shell's home is the projects workspace. */
export default function Home() {
  redirect("/projects");
}
