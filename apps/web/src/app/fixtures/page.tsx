import { Shell } from "@/components/trials/Shell";
import { copy } from "@/desk/copy";

export const metadata = { title: "Matchproof Narrator Trials: Fixtures" };

export default function Page() {
  return (
    <Shell>
      <h1 className="tr-h1">{copy.en.trials.fixtures.title}</h1>
      <p className="tr-body">{copy.en.trials.fixtures.soon}</p>
    </Shell>
  );
}
