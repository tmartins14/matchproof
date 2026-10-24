interface WordmarkProps {
  first: string;
  second: string;
}

export function Wordmark({ first, second }: WordmarkProps) {
  return (
    <div className="mp-lift">
      <div className="mp-wordmark">
        <span>{first}</span>
        <span>{second}</span>
      </div>
    </div>
  );
}
