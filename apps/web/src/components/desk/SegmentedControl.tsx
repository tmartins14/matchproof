interface Option<T extends string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}

export type SegmentCut = "cutStart" | "cutEnd" | "cut";

/** The cut a chip takes from its place in the group: a straight outer side at each end, so it runs parallel to the border. */
export function segmentCut(index: number, count: number): SegmentCut {
  if (count > 1 && index === 0) return "cutStart";
  if (count > 1 && index === count - 1) return "cutEnd";
  return "cut";
}

const CUT_CLASS: Record<SegmentCut, string> = { cutStart: "mp-cut-start", cutEnd: "mp-cut-end", cut: "mp-cut" };

export function SegmentedControl<T extends string>({ label, options, value, onChange, disabled }: SegmentedControlProps<T>) {
  return (
    <div className="mp-seg" role="group" aria-label={label}>
      {options.map((option, index) => {
        const cut = segmentCut(index, options.length);
        return (
          <button key={option.value} type="button" className={CUT_CLASS[cut]} data-cut={cut} aria-pressed={option.value === value} disabled={disabled} onClick={() => onChange(option.value)}>
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
