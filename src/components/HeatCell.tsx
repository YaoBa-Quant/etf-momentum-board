import clsx from "clsx";
import { getTierStyle } from "@/components/tierColors";

// 连续动量着色（无档位时的回退方案）
const getHeatClassName = (value: number) => {
  if (value >= 7) return "bg-[#f8696b] text-[#7f1d1d]";
  if (value >= 4) return "bg-[#f39c12] text-[#7c2d12]";
  if (value >= 1) return "bg-[#f7dc6f] text-[#6b4f00]";
  if (value > -1) return "bg-[#f7f3cf] text-[#5f6b6d]";
  if (value > -4) return "bg-[#d5e8d4] text-[#3d5a40]";
  if (value > -7) return "bg-[#b7d7b0] text-[#355e3b]";
  return "bg-[#93c47d] text-[#274b2f]";
};

interface HeatCellProps {
  value: number | null;
  compact?: boolean;
  fluid?: boolean;
  hideValue?: boolean;
  nullDisplayText?: string;
  nullTitle?: string;
  nullClassName?: string;
  className?: string;
  rank?: number | null;
  tier?: string | null;
  poolSize?: number | null;
}

export function HeatCell({
  value,
  compact = false,
  fluid = false,
  hideValue = false,
  nullDisplayText = "--",
  nullTitle,
  nullClassName,
  className,
  rank,
  tier,
  poolSize,
}: HeatCellProps) {
  if (value === null || Number.isNaN(value)) {
    return (
      <div
        title={nullTitle}
        className={clsx(
          "relative flex h-8 items-center justify-center rounded-sm border border-[#d9dccf] bg-[#f7f3cf] text-[10px] font-semibold leading-none text-[#9ca3af]",
          fluid ? "min-w-0 w-full px-0.5" : "min-w-[45px]",
          compact && !fluid ? "min-w-[42px] text-[10px]" : "",
          nullClassName,
          className,
        )}
      >
        {hideValue ? "" : nullDisplayText}
      </div>
    );
  }

  const tierStyle = getTierStyle(tier);
  const showTier = tierStyle !== null && rank !== null && rank !== undefined;

  if (showTier) {
    return (
      <div
        title={`名次：${rank}/${poolSize ?? "?"}（${tier}）\n20日斜率动量：${value > 0 ? "+" : ""}${value.toFixed(4)}`}
        style={{ backgroundColor: tierStyle.bg, color: tierStyle.text }}
        className={clsx(
          "relative flex h-8 flex-col items-center justify-center gap-[1px] rounded-sm border border-[#d9dccf] leading-none",
          fluid ? "min-w-0 w-full px-1" : "min-w-[45px]",
          compact && !fluid ? "min-w-[42px]" : "",
          className,
        )}
      >
        <span className="text-[11px] font-semibold tabular-nums">{rank}</span>
        {!hideValue && (
          <span className="text-[9px] opacity-80 tabular-nums">
            {value > 0 ? "+" : ""}
            {value.toFixed(1)}
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      title={`20日斜率动量：${value > 0 ? "+" : ""}${value.toFixed(4)}`}
      className={clsx(
        "relative flex h-8 items-center justify-center rounded-sm border border-[#d9dccf] pr-2 text-[11px] font-semibold leading-none",
        fluid ? "min-w-0 w-full px-1 pr-1" : "min-w-[45px]",
        compact && !fluid ? "min-w-[42px] text-[10px]" : "",
        fluid && compact ? "text-[10px]" : "",
        getHeatClassName(value),
        className,
      )}
    >
      {!hideValue && (
        <>
          {value > 0 ? "+" : ""}
          {value.toFixed(1)}
        </>
      )}
    </div>
  );
}
