/** Turn technical server messages into plain words that say what happened and what to do. */
export function plain(m: string, status = 0): string {
  const rules: [RegExp, string | ((x: RegExpMatchArray) => string)][] = [
    [/Not authenticated|Invalid or expired token/i, "Нужно войти в систему заново."],
    [/Missing permission/i, "У вас нет прав на это действие. Обратитесь к администратору."],
    [/Procurement not found/i, "Закупка не найдена или у вас нет к ней доступа."],
    [/is locked; create a new version/i, "Документ утверждён и закрыт для правок. Чтобы изменить его, создайте новую версию на шаге «3. Excel»."],
    [/Transition .* is not allowed/i, "Сейчас это действие недоступно: документ находится в другом статусе."],
    [/must be confirmed/i, "Подтвердите действие ещё раз."],
    [/A comment is required/i, "Напишите комментарий — без него это действие недоступно."],
    [/Add at least one item/i, "Добавьте в закупку хотя бы один товар."],
    [/Record the supplier selection/i, "Сначала выберите поставщика и напишите обоснование (шаг «2. Сравнение» → «Итоги поставщиков»)."],
    [/cannot approve their own/i, "Нельзя утвердить свой собственный документ. Попросите коллегу."],
    [/(\d+) offer lines still await/i, (x) => `Есть позиции, которые ещё нужно подтвердить или проверить технически (${x[1]}). Откройте предложения и завершите проверку.`],
    [/Selected offer is incomplete/i, "У этого поставщика нет цен на все товары. Выберите другого поставщика."],
    [/Too many failed attempts/i, "Слишком много неудачных попыток входа. Подождите 15 минут и попробуйте снова."],
    [/greater than 0|greater than zero/i, "Число должно быть больше нуля."],
    [/valid (decimal|number)|Decimal/i, "Введите число (цифры, точка или запятая)."],
    [/at least \d+ characters/i, "Слишком короткое значение."],
    [/larger than \d+ MB/i, "Файл слишком большой."],
    [/Failed to fetch|NetworkError|Load failed/i, "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз."],
  ];
  for (const [re, out] of rules) {
    const x = m.match(re);
    if (x) return typeof out === "function" ? out(x) : out;
  }
  if (status >= 500) return "На сервере произошла ошибка. Попробуйте ещё раз через минуту.";
  return m;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(plain(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`, status));
  }
}

export const token = {
  get: () => (typeof window === "undefined" ? null : localStorage.getItem("pp_token")),
  set: (t: string) => localStorage.setItem("pp_token", t),
  clear: () => localStorage.removeItem("pp_token"),
};

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  } catch (e: any) {
    throw new ApiError(0, plain(String(e?.message ?? "Failed to fetch")));
  }
  if (res.status === 401 && typeof window !== "undefined" && !/\/auth\/(login|phone-login|device-status)/.test(path)) {
    token.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail ?? j;
      if (Array.isArray(detail)) detail = detail.map((d: any) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function download(path: string, filename: string) {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${token.get()}` } });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

/** Group digits of a decimal STRING (never via float): "1234567.5" -> "1 234 567.50" */
export function fmt(s: string | null | undefined): string {
  if (s == null) return "—";
  const [i, d] = s.split(".");
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, " ") + (d && /[1-9]/.test(d) ? "." + d : "");
}

export const STATUS_RU: Record<string, string> = {
  DRAFT: "Черновик", PREPARED: "Подготовлено", IN_REVIEW: "На проверке", IN_APPROVAL: "На согласовании",
  APPROVED: "Утверждено", RETURNED: "Возвращено", REJECTED: "Отклонено",
  UPLOADED: "Загружено", QUEUED: "В очереди", ANALYZING: "Анализируется", NEEDS_REVIEW: "Требуется проверка", PROCESSED: "Обработано", ERROR: "Ошибка обработки",
};

export const FLAG_RU: Record<string, string> = {
  dimensions_mismatch: "Размеры не совпадают", standard_mismatch: "Другой стандарт (ГОСТ/ТУ)", material_grade_mismatch: "Другая марка материала",
  dimensions_not_stated: "Размеры не указаны", standard_not_stated: "Стандарт не указан", material_grade_not_stated: "Марка не указана",
  numeric_parameters_differ: "Числовые параметры различаются", unit_mismatch: "Разные единицы измерения",
  fewer_than_3_offers: "Меньше 3 предложений", no_complete_comparable_offer: "Нет полного сопоставимого предложения",
  offer_not_confirmed: "Предложение не подтверждено", delivery_unknown: "Доставка не указана", delivery_days_unknown: "Срок поставки не указан",
  delivery_too_late: "Срок поставки позже потребности",
  price_missing: "Нет цены", quantity_missing: "Нет количества", unit_missing: "Нет единицы", sum_mismatch: "Сумма ≠ кол-во × цена",
  price_derived_from_total: "Цена вычислена из суммы", quote_not_found_in_source: "Фрагмент не найден в источнике",
  price_not_found_in_source: "Цена не найдена в источнике", name_not_found_in_source: "Название не найдено в источнике",
  no_lines_extracted: "Позиции в файле не найдены — проверьте файл или введите цены вручную",
  analog_offered: "Поставщик предлагает аналог",
  ocr_text_may_contain_errors: "Текст OCR может содержать ошибки",
};
