import { copy } from "@/desk/copy";

const WORD = { S: "STANDS", A: "AMENDED", O: "OVERTURNED", H: "HELD" } as const;

/** The last five scored claims as S/A/O/H chips: a letter on a verdict-token fill. */
export function FormChips({ form }: { form: readonly string[] }) {
  const t = copy.en.trials.verdictLong;
  return (
    <div className="tr-form">
      {form.map((letter, i) => (
        <span key={i} className={`tr-chip-form tr-chip-form--${letter}`} title={t[WORD[letter as keyof typeof WORD]]}>
          {letter}
        </span>
      ))}
    </div>
  );
}
