const DAY_MS = 24 * 60 * 60 * 1000;

const formatDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const isTradingDay = (date: Date) => {
  const day = date.getDay();
  return day !== 0 && day !== 6;
};

export const getTradingDays = (count: number, endDate = new Date()) => {
  const result: string[] = [];
  let cursor = new Date(endDate);

  while (result.length < count) {
    if (isTradingDay(cursor)) {
      result.unshift(formatDate(cursor));
    }
    cursor = new Date(cursor.getTime() - DAY_MS);
  }

  return result;
};
