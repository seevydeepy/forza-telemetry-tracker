export interface FixedWindowResult {
  windowStart: number;
  count: number;
}

export async function incrementFixedWindow(
  db: D1Database,
  key: string,
  nowSeconds: number,
  windowSeconds: number
): Promise<FixedWindowResult> {
  const windowStart = Math.floor(nowSeconds / windowSeconds) * windowSeconds;
  const row = await db
    .prepare(
      `INSERT INTO rate_limits (key, window_start, count)
       VALUES (?, ?, 1)
       ON CONFLICT(key) DO UPDATE SET
         window_start = CASE
           WHEN rate_limits.window_start = excluded.window_start THEN rate_limits.window_start
           ELSE excluded.window_start
         END,
         count = CASE
           WHEN rate_limits.window_start = excluded.window_start THEN rate_limits.count + 1
           ELSE 1
         END
       RETURNING window_start AS windowStart, count`
    )
    .bind(key, windowStart)
    .first<FixedWindowResult>();

  if (row === null) {
    throw new Error("rate limit update did not return a row");
  }

  return row;
}
