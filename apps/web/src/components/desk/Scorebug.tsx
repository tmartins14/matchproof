interface ScorebugProps {
  label: string;
  homeShort: string;
  awayShort: string;
  home: number;
  away: number;
  clock: string;
  status: "live" | "fullTime";
  statusText: string;
}

export function Scorebug({ label, homeShort, awayShort, home, away, clock, status, statusText }: ScorebugProps) {
  return (
    <div className="mp-lift">
      <div className="mp-scorebug num" role="group" aria-label={label}>
        <span className="mp-team mp-team--home">{homeShort}</span>
        <span className="mp-score">
          {home}
          <span className="mp-muted">–</span>
          {away}
        </span>
        <span className="mp-team mp-team--away">{awayShort}</span>
        <span className="mp-clock">{clock}</span>
        {status === "live" ? (
          <span className="mp-live">
            <i className="pulse" aria-hidden="true" />
            {statusText}
          </span>
        ) : (
          <span className="mp-live">{statusText}</span>
        )}
      </div>
    </div>
  );
}
