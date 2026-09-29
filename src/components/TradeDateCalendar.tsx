import { useEffect, useMemo, useState } from "react";

interface TradeDateCalendarProps {
  availableTradeDates: string[];
  selectedTradeDate: string;
  disabled?: boolean;
  onSelect: (tradeDate: string) => void;
}

const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"];

function formatTradeDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getMonthCells(visibleMonth: string) {
  const [year, month] = visibleMonth.split("-").map(Number);
  const firstDay = new Date(year, month - 1, 1);
  const daysInMonth = new Date(year, month, 0).getDate();
  const startOffset = (firstDay.getDay() + 6) % 7;
  const cells: Array<{ key: string; tradeDate: string | null; dayLabel: string }> = [];

  for (let index = 0; index < 42; index += 1) {
    const dayNumber = index - startOffset + 1;
    if (dayNumber < 1 || dayNumber > daysInMonth) {
      cells.push({
        key: `blank-${visibleMonth}-${index}`,
        tradeDate: null,
        dayLabel: "",
      });
      continue;
    }

    const tradeDate = formatTradeDate(new Date(year, month - 1, dayNumber));
    cells.push({
      key: tradeDate,
      tradeDate,
      dayLabel: String(dayNumber),
    });
  }

  return cells;
}

export function TradeDateCalendar({
  availableTradeDates,
  selectedTradeDate,
  disabled = false,
  onSelect,
}: TradeDateCalendarProps) {
  const availableDateSet = useMemo(() => new Set(availableTradeDates), [availableTradeDates]);
  const availableMonths = useMemo(() => {
    const months = new Set<string>();
    for (const tradeDate of availableTradeDates) {
      months.add(tradeDate.slice(0, 7));
    }
    return Array.from(months).sort((left, right) => right.localeCompare(left));
  }, [availableTradeDates]);

  const [visibleMonth, setVisibleMonth] = useState(selectedTradeDate.slice(0, 7));

  useEffect(() => {
    const nextMonth = selectedTradeDate.slice(0, 7);
    setVisibleMonth((currentMonth) => (currentMonth === nextMonth ? currentMonth : nextMonth));
  }, [selectedTradeDate]);

  useEffect(() => {
    if (availableMonths.length === 0) {
      return;
    }
    if (!availableMonths.includes(visibleMonth)) {
      setVisibleMonth(availableMonths[0]);
    }
  }, [availableMonths, visibleMonth]);

  const visibleMonthIndex = availableMonths.indexOf(visibleMonth);
  const newerMonth = visibleMonthIndex > 0 ? availableMonths[visibleMonthIndex - 1] : null;
  const olderMonth =
    visibleMonthIndex >= 0 && visibleMonthIndex < availableMonths.length - 1
      ? availableMonths[visibleMonthIndex + 1]
      : null;

  const monthCells = useMemo(() => getMonthCells(visibleMonth), [visibleMonth]);
  const selectedYear = visibleMonth.slice(0, 4);
  const selectedMonth = visibleMonth.slice(5, 7);
  const yearOptions = useMemo(() => {
    const years = new Set<string>();
    for (const month of availableMonths) {
      years.add(month.slice(0, 4));
    }
    return Array.from(years).sort((left, right) => right.localeCompare(left));
  }, [availableMonths]);
  const monthOptions = useMemo(
    () =>
      availableMonths
        .filter((month) => month.startsWith(`${selectedYear}-`))
        .map((month) => month.slice(5, 7)),
    [availableMonths, selectedYear],
  );

  const monthLabel =
    visibleMonth.length === 7 ? `${visibleMonth.slice(0, 4)}年${visibleMonth.slice(5, 7)}月` : visibleMonth;

  return (
    <div className="absolute right-0 top-[calc(100%+8px)] z-[120] isolate w-[360px] rounded-lg border border-[#d8ddcf] bg-[#fbfbf6] p-3 shadow-lg">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <div className="text-[12px] font-semibold text-[#374151]">选择交易日</div>
          <div className="text-[11px] text-[#6b7280]">仅交易日可点击，支持按月切换</div>
        </div>
        <div className="text-[12px] font-semibold text-[#374151]">{monthLabel}</div>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => olderMonth && setVisibleMonth(olderMonth)}
          disabled={!olderMonth}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#dde2d6] bg-white text-[14px] text-[#4b5563] transition hover:border-[#c5ccbc] hover:bg-[#f7f8f2] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {"<"}
        </button>
        <select
          value={selectedYear}
          onChange={(event) => {
            const nextYear = event.target.value;
            const nextMonth = availableMonths.find((month) => month.startsWith(`${nextYear}-`));
            if (nextMonth) {
              setVisibleMonth(nextMonth);
            }
          }}
          disabled={disabled}
          className="h-8 rounded-md border border-[#dde2d6] bg-white px-2 text-[12px] text-[#374151] outline-none"
        >
          {yearOptions.map((year) => (
            <option key={year} value={year}>
              {year}年
            </option>
          ))}
        </select>
        <select
          value={selectedMonth}
          onChange={(event) => setVisibleMonth(`${selectedYear}-${event.target.value}`)}
          disabled={disabled}
          className="h-8 rounded-md border border-[#dde2d6] bg-white px-2 text-[12px] text-[#374151] outline-none"
        >
          {monthOptions.map((month) => (
            <option key={month} value={month}>
              {month}月
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => newerMonth && setVisibleMonth(newerMonth)}
          disabled={!newerMonth}
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md border border-[#dde2d6] bg-white text-[14px] text-[#4b5563] transition hover:border-[#c5ccbc] hover:bg-[#f7f8f2] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {">"}
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="flex h-7 items-center justify-center text-[11px] font-medium text-[#6b7280]">
            {label}
          </div>
        ))}

        {monthCells.map((cell) => {
          if (!cell.tradeDate) {
            return <div key={cell.key} className="h-10 rounded-md bg-transparent" />;
          }

          const isAvailable = availableDateSet.has(cell.tradeDate);
          const isSelected = cell.tradeDate === selectedTradeDate;
          return (
            <button
              key={cell.key}
              type="button"
              disabled={!isAvailable || disabled}
              onClick={() => onSelect(cell.tradeDate!)}
              className={`h-10 rounded-md border text-[12px] transition ${
                isSelected
                  ? "border-[#c9a227] bg-[#fff6d8] font-semibold text-[#8a5b00]"
                  : isAvailable
                    ? "border-[#dde2d6] bg-white text-[#4b5563] hover:border-[#c5ccbc] hover:bg-[#f7f8f2]"
                    : "border-[#eef1e8] bg-[#f5f6ef] text-[#b5bcb0]"
              }`}
            >
              {cell.dayLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}
