export function PitchMarkings() {
  return (
    <svg viewBox="0 0 120 80" preserveAspectRatio="none" aria-hidden="true">
      <g fill="none" stroke="var(--mp-pitchLine)" strokeWidth="0.35" vectorEffect="non-scaling-stroke">
        <rect x="0.5" y="0.5" width="119" height="79" />
        <line x1="60" y1="0.5" x2="60" y2="79.5" />
        <circle cx="60" cy="40" r="10" />
        <rect x="0.5" y="18" width="17.5" height="44" />
        <rect x="0.5" y="30" width="5.5" height="20" />
        <rect x="102" y="18" width="17.5" height="44" />
        <rect x="114" y="30" width="5.5" height="20" />
        <path d="M18 32 A10 10 0 0 1 18 48" />
        <path d="M102 32 A10 10 0 0 0 102 48" />
      </g>
      <g fill="var(--mp-pitchLine)">
        <circle cx="60" cy="40" r="0.6" />
        <circle cx="12" cy="40" r="0.6" />
        <circle cx="108" cy="40" r="0.6" />
      </g>
    </svg>
  );
}
