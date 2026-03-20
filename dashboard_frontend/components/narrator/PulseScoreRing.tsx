'use client';

interface PulseScoreRingProps {
  score: number;       // 0-100
  delta?: number | null;
  size?: number;
}

function gradeColor(score: number): string {
  if (score >= 80) return 'var(--ok)';
  if (score >= 60) return 'var(--uplink)';
  if (score >= 40) return 'var(--warn)';
  return 'var(--signal)';
}

function gradeLabel(score: number): string {
  if (score >= 80) return 'A';
  if (score >= 60) return 'B';
  if (score >= 40) return 'C';
  return 'D';
}

export function PulseScoreRing({ score, delta, size = 160 }: PulseScoreRingProps) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = gradeColor(score);
  const grade = gradeLabel(score);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          {/* Track */}
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke="var(--wire)" strokeWidth={strokeWidth}
          />
          {/* Progress */}
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={color} strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1s ease-out' }}
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-bold" style={{ color }}>{score}</span>
          <span
            className="text-xs font-bold uppercase tracking-widest"
            style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}
          >
            Grade {grade}
          </span>
        </div>
      </div>
      {/* Delta */}
      {delta != null && (
        <span
          className="text-xs font-mono font-medium"
          style={{ color: delta > 0 ? 'var(--ok)' : delta < 0 ? 'var(--signal)' : 'var(--on-low)' }}
        >
          {delta > 0 ? '+' : ''}{delta} vs last period
        </span>
      )}
      <span
        className="text-xs uppercase tracking-widest"
        style={{ color: 'var(--on-low)', fontFamily: 'var(--font-condensed)' }}
      >
        Fleet Pulse
      </span>
    </div>
  );
}
