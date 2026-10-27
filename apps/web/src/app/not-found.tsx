import Link from "next/link";
import { copy } from "@/desk/copy";
import { Shell } from "@/components/trials/Shell";

export const metadata = { title: "Matchproof Narrator Trials: Not found" };

export default function NotFound() {
  const t = copy.en.trials.notFound;
  return (
    <Shell>
      <h1 className="tr-h1">{t.title}</h1>
      <p className="tr-sub">{t.body}</p>
      <p>
        <Link href="/" className="tr-link">
          {t.home}
        </Link>
      </p>
    </Shell>
  );
}
