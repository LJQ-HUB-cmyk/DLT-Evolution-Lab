type BallProps = {
  value: number;
  color: "red" | "blue";
};

export function Ball({ value, color }: BallProps) {
  return <span className={`ball ball-${color}`}>{String(value).padStart(2, "0")}</span>;
}

