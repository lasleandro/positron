import { formatDuration } from "../lib/format";

interface Props {
  id: string;
  label: string;
  options: number[];
  value: number;
  onChange: (minutes: number) => void;
}

/** Segmented control: short lifetimes are the default, and the choice is always visible. */
export function DurationSelect({ id, label, options, value, onChange }: Props) {
  return (
    <div role="radiogroup" aria-labelledby={id}>
      <span id={id} className="field-label">{label}</span>
      <div className="segmented">
        {options.map((minutes) => (
          <button key={minutes} type="button" role="radio" aria-checked={value === minutes}
            className={value === minutes ? "segment on" : "segment"} onClick={() => onChange(minutes)}>
            {formatDuration(minutes)}
          </button>
        ))}
      </div>
    </div>
  );
}
