const state = {
  columns: [],
  indexes: [],
  selectedColumn: "",
  items: [],
  nextCursor: null,
  loading: false,
  lastQueryType: "search",
  expandedRows: new Set(),
}

const elements = {
  connectionStatus: document.querySelector("#connectionStatus"),
  connectionText: document.querySelector("#connectionText"),
  tableNameLabel: document.querySelector("#tableNameLabel"),
  searchForm: document.querySelector("#searchForm"),
  searchInput: document.querySelector("#searchInput"),
  modeSelect: document.querySelector("#modeSelect"),
  limitSelect: document.querySelector("#limitSelect"),
  tokenInput: document.querySelector("#tokenInput"),
  saveTokenButton: document.querySelector("#saveTokenButton"),
  clearButton: document.querySelector("#clearButton"),
  searchButton: document.querySelector("#searchButton"),
  columnPills: document.querySelector("#columnPills"),
  columnCount: document.querySelector("#columnCount"),
  resultMeta: document.querySelector("#resultMeta"),
  stateMessage: document.querySelector("#stateMessage"),
  resultHead: document.querySelector("#resultHead"),
  resultBody: document.querySelector("#resultBody"),
  loadMoreButton: document.querySelector("#loadMoreButton"),
  gsiForm: document.querySelector("#gsiForm"),
  indexSelect: document.querySelector("#indexSelect"),
  indexCount: document.querySelector("#indexCount"),
  partitionKeyLabel: document.querySelector("#partitionKeyLabel"),
  partitionValueInput: document.querySelector("#partitionValueInput"),
  sortModeField: document.querySelector("#sortModeField"),
  sortModeSelect: document.querySelector("#sortModeSelect"),
  sortKeyLabel: document.querySelector("#sortKeyLabel"),
  sortValueField: document.querySelector("#sortValueField"),
  sortValueInput: document.querySelector("#sortValueInput"),
  sortValueToField: document.querySelector("#sortValueToField"),
  sortValueToInput: document.querySelector("#sortValueToInput"),
  gsiQueryButton: document.querySelector("#gsiQueryButton"),
}

const TOKEN_STORAGE_KEY = "tourKoreaDomainDataViewerToken"

const COLUMN_LABELS = {
  PK: "파티션 키",
  SK: "정렬 키",
  category: "카테고리",
  city_key: "도시 키",
  city_name: "도시명",
  country: "국가",
  domain_sort_key: "도메인 정렬 키",
  entity_type: "엔티티 유형",
  province: "광역지역",
  province_key: "광역지역 키",
  quality_status: "품질 상태",
  season: "계절",
  source: "출처",
  theme_tags: "테마 태그",
  title: "제목",
  updated_at: "수정 일시",
}

const VALUE_LABELS = {
  category: {
    heritage: "문화유산",
  },
  country: {
    KR: "대한민국",
    JP: "일본",
  },
  entity_type: {
    attraction: "관광지",
    city: "도시",
    festival: "축제",
  },
  quality_status: {
    approved: "승인됨",
    needs_review: "검토 필요",
    pending: "대기",
    rejected: "반려",
  },
  season: {
    autumn: "가을",
    spring: "봄",
    summer: "여름",
    winter: "겨울",
  },
  source: {
    manual: "수동 입력",
    tourapi: "관광공사 API",
  },
  theme_tags: {
    coffee: "커피",
    festival: "축제",
    sea: "바다",
  },
}

function getToken() {
  return sessionStorage.getItem(TOKEN_STORAGE_KEY) || ""
}

function setToken(value) {
  const token = value.trim()
  if (token) {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
  } else {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}

async function apiGet(path, params = {}) {
  const url = new URL(path, window.location.origin)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value)
    }
  })

  const headers = {}
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(url, { headers })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = body.message || `요청에 실패했습니다. (${response.status})`
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return body
}

async function loadColumns() {
  setConnection("loading", "연결 중")
  setStateMessage("컬럼을 불러오는 중입니다.")
  try {
    const data = await apiGet("/api/columns")
    state.columns = data.columns || []
    elements.tableNameLabel.textContent = data.tableName || "TourKoreaDomainData"
    renderPills()
    setConnection("ready", data.authMode === "required" ? "토큰 적용" : "연결됨")
    setStateMessage("")
  } catch (error) {
    setConnection("error", "오류")
    setStateMessage(error.message, "error")
  }
}

async function loadIndexes() {
  try {
    const data = await apiGet("/api/indexes")
    state.indexes = data.indexes || []
    renderIndexes()
  } catch (error) {
    setConnection("error", "오류")
    setStateMessage(error.message, "error")
  }
}

async function runSearch({ append = false } = {}) {
  if (state.loading) {
    return
  }
  state.loading = true
  state.lastQueryType = "search"
  elements.searchButton.disabled = true
  elements.loadMoreButton.disabled = true
  setStateMessage("검색 중입니다.")

  const params = {
    q: elements.searchInput.value.trim(),
    column: state.selectedColumn,
    mode: elements.modeSelect.value,
    limit: elements.limitSelect.value,
    cursor: append ? state.nextCursor : "",
  }

  try {
    const data = await apiGet("/api/search", params)
    const incoming = data.items || []
    state.items = append ? state.items.concat(incoming) : incoming
    state.nextCursor = data.nextCursor || null
    state.columns = mergeColumns(state.columns, data.columns || [], state.items)
    renderPills()
    renderResults()
    updateMeta(data)
    setConnection("ready", data.authMode === "required" ? "토큰 적용" : "연결됨")
    if (data.scanLimitReached) {
      setStateMessage("스캔 제한에 도달했습니다. 검색어 또는 컬럼을 좁혀 다시 조회하세요.", "warn")
    } else if (state.items.length === 0) {
      setStateMessage("결과가 없습니다.")
    } else {
      setStateMessage("")
    }
  } catch (error) {
    setConnection("error", "오류")
    setStateMessage(error.message, "error")
  } finally {
    state.loading = false
    elements.searchButton.disabled = false
    elements.loadMoreButton.disabled = false
    elements.loadMoreButton.hidden = !state.nextCursor
  }
}

async function runIndexQuery({ append = false } = {}) {
  if (state.loading) {
    return
  }

  const index = selectedIndex()
  if (!index) {
    setStateMessage("GSI 인덱스를 선택하세요.", "error")
    return
  }
  if (!elements.partitionValueInput.value.trim()) {
    setStateMessage("파티션 키 값을 입력하세요.", "error")
    return
  }

  state.loading = true
  state.lastQueryType = "gsi"
  elements.gsiQueryButton.disabled = true
  elements.loadMoreButton.disabled = true
  setStateMessage("GSI를 조회하는 중입니다.")

  const params = {
    indexName: index.indexName,
    partitionValue: elements.partitionValueInput.value.trim(),
    sortMode: elements.sortModeSelect.value,
    sortValue: elements.sortValueInput.value.trim(),
    sortValueTo: elements.sortValueToInput.value.trim(),
    limit: elements.limitSelect.value,
    cursor: append ? state.nextCursor : "",
  }

  try {
    const data = await apiGet("/api/query-index", params)
    const incoming = data.items || []
    state.items = append ? state.items.concat(incoming) : incoming
    state.nextCursor = data.nextCursor || null
    state.columns = mergeColumns(state.columns, data.columns || [], state.items)
    renderPills()
    renderResults()
    updateMeta(data)
    setConnection("ready", data.authMode === "required" ? "토큰 적용" : "연결됨")
    setStateMessage(state.items.length === 0 ? "결과가 없습니다." : "")
  } catch (error) {
    setConnection("error", "오류")
    setStateMessage(error.message, "error")
  } finally {
    state.loading = false
    elements.gsiQueryButton.disabled = false
    elements.loadMoreButton.disabled = !state.nextCursor
    elements.loadMoreButton.hidden = !state.nextCursor
  }
}

function renderPills() {
  const pills = []
  pills.push(createPill("전체 컬럼", "", state.selectedColumn === ""))
  state.columns.forEach((column) => {
    pills.push(createPill(displayColumnName(column), column, state.selectedColumn === column))
  })
  elements.columnPills.replaceChildren(...pills)
  elements.columnCount.textContent = String(state.columns.length)
}

function renderIndexes() {
  const options = []
  if (state.indexes.length === 0) {
    const option = document.createElement("option")
    option.value = ""
    option.textContent = "GSI 없음"
    options.push(option)
  } else {
    state.indexes.forEach((index) => {
      const option = document.createElement("option")
      option.value = index.indexName
      option.textContent = index.indexName
      options.push(option)
    })
  }
  elements.indexSelect.replaceChildren(...options)
  elements.indexCount.textContent = `${state.indexes.length}개`
  elements.gsiQueryButton.disabled = state.indexes.length === 0
  updateGsiKeyLabels()
}

function createPill(label, column, pressed) {
  const item = document.createElement("span")
  item.setAttribute("role", "listitem")

  const button = document.createElement("button")
  button.type = "button"
  button.className = "column-pill"
  button.setAttribute("aria-pressed", pressed ? "true" : "false")
  button.textContent = label
  if (column) {
    button.title = column
  }
  button.addEventListener("click", () => {
    state.selectedColumn = column
    state.nextCursor = null
    state.expandedRows.clear()
    renderPills()
    runSearch()
  })
  item.append(button)
  return item
}

function renderResults() {
  const visibleColumns = getVisibleColumns()
  const headCells = [createHeaderCell("상세"), ...visibleColumns.map((column) => createHeaderCell(displayColumnName(column)))]
  elements.resultHead.replaceChildren(...headCells)

  const rows = []
  state.items.forEach((item, index) => {
    const row = document.createElement("tr")
    const actionCell = document.createElement("td")
    actionCell.className = "row-action-cell"
    const button = document.createElement("button")
    button.type = "button"
    button.className = "secondary-button json-button"
    button.textContent = state.expandedRows.has(index) ? "닫기" : "상세"
    button.addEventListener("click", () => toggleRow(index))
    actionCell.append(button)
    row.append(actionCell)

    visibleColumns.forEach((column) => {
      const cell = document.createElement("td")
      cell.title = formatValue(item[column])
      cell.textContent = displayCellValue(column, item[column])
      row.append(cell)
    })
    rows.push(row)

    if (state.expandedRows.has(index)) {
      const detailRow = document.createElement("tr")
      detailRow.className = "detail-row"
      const detailCell = document.createElement("td")
      detailCell.colSpan = visibleColumns.length + 1
      const pre = document.createElement("pre")
      pre.textContent = JSON.stringify(item, null, 2)
      detailCell.append(pre)
      detailRow.append(detailCell)
      rows.push(detailRow)
    }
  })

  elements.resultBody.replaceChildren(...rows)
}

function toggleRow(index) {
  if (state.expandedRows.has(index)) {
    state.expandedRows.delete(index)
  } else {
    state.expandedRows.add(index)
  }
  renderResults()
}

function getVisibleColumns() {
  const preferred = ["PK", "SK", "city_key", "province_key", "domain_sort_key", "entity_type", "country", "province", "city_name", "title", "quality_status"]
  const available = new Set(state.columns)
  const selected = state.selectedColumn ? [state.selectedColumn] : []
  const ordered = [...selected, ...preferred, ...state.columns]
  const unique = []
  ordered.forEach((column) => {
    if (column && available.has(column) && !unique.includes(column)) {
      unique.push(column)
    }
  })
  return unique.slice(0, 10)
}

function createHeaderCell(label) {
  const cell = document.createElement("th")
  cell.scope = "col"
  cell.textContent = label
  return cell
}

function displayColumnName(column) {
  return COLUMN_LABELS[column] || column
}

function displayCellValue(column, value) {
  if (Array.isArray(value)) {
    return value.map((item) => displayScalarValue(column, item)).join(", ")
  }
  return displayScalarValue(column, value)
}

function displayScalarValue(column, value) {
  if (value === undefined || value === null) {
    return ""
  }
  if (Array.isArray(value) || typeof value === "object") {
    return JSON.stringify(value)
  }
  const raw = String(value)
  return VALUE_LABELS[column]?.[raw] || raw
}

function formatValue(value) {
  if (value === undefined || value === null) {
    return ""
  }
  if (Array.isArray(value) || typeof value === "object") {
    return JSON.stringify(value)
  }
  return String(value)
}

function mergeColumns(existing, apiColumns, items) {
  const next = new Set(existing)
  apiColumns.forEach((column) => next.add(column))
  items.forEach((item) => Object.keys(item).forEach((column) => next.add(column)))
  return [...next].sort((a, b) => a.localeCompare(b))
}

function updateMeta(data) {
  const parts = [`${state.items.length}건`]
  if (data.scannedCount !== undefined) {
    parts.push(`${data.scannedCount}건 스캔`)
  }
  if (data.queryType === "gsi" && data.indexName) {
    parts.push(`GSI: ${data.indexName}`)
  }
  if (state.selectedColumn) {
    parts.push(displayColumnName(state.selectedColumn))
  }
  elements.resultMeta.textContent = parts.join(" · ")
}

function selectedIndex() {
  return state.indexes.find((index) => index.indexName === elements.indexSelect.value) || null
}

function getIndexKey(index, keyType) {
  return index?.keySchema?.find((key) => key.keyType === keyType)?.attributeName || ""
}

function updateGsiKeyLabels() {
  const index = selectedIndex()
  const partitionKey = getIndexKey(index, "HASH")
  const sortKey = getIndexKey(index, "RANGE")
  const sortMode = elements.sortModeSelect.value

  elements.partitionKeyLabel.textContent = partitionKey ? `${displayColumnName(partitionKey)} 값` : "파티션 키 값"
  elements.sortKeyLabel.textContent = sortKey ? `${displayColumnName(sortKey)} 조건` : "정렬 키 조건"
  elements.sortModeField.hidden = !sortKey
  elements.sortValueField.hidden = !sortKey || !sortMode
  elements.sortValueToField.hidden = sortMode !== "between"
  elements.sortValueInput.disabled = !sortKey || !sortMode
  elements.sortValueToInput.disabled = sortMode !== "between"
}

function setStateMessage(message, tone = "") {
  elements.stateMessage.textContent = message
  if (tone) {
    elements.stateMessage.dataset.tone = tone
  } else {
    delete elements.stateMessage.dataset.tone
  }
}

function setConnection(status, text) {
  elements.connectionStatus.className = `status-dot status-${status}`
  elements.connectionText.textContent = text
}

elements.searchForm.addEventListener("submit", (event) => {
  event.preventDefault()
  state.nextCursor = null
  state.expandedRows.clear()
  runSearch()
})

elements.clearButton.addEventListener("click", () => {
  elements.searchInput.value = ""
  state.selectedColumn = ""
  state.nextCursor = null
  state.expandedRows.clear()
  renderPills()
  runSearch()
})

elements.loadMoreButton.addEventListener("click", () => {
  if (state.nextCursor) {
    if (state.lastQueryType === "gsi") {
      runIndexQuery({ append: true })
    } else {
      runSearch({ append: true })
    }
  }
})

elements.saveTokenButton.addEventListener("click", () => {
  setToken(elements.tokenInput.value)
  Promise.all([loadColumns(), loadIndexes()]).then(() => runSearch())
})

elements.gsiForm.addEventListener("submit", (event) => {
  event.preventDefault()
  state.nextCursor = null
  state.expandedRows.clear()
  runIndexQuery()
})

elements.indexSelect.addEventListener("change", () => {
  state.nextCursor = null
  elements.sortModeSelect.value = ""
  elements.sortValueInput.value = ""
  elements.sortValueToInput.value = ""
  updateGsiKeyLabels()
})

elements.sortModeSelect.addEventListener("change", updateGsiKeyLabels)

elements.tokenInput.value = getToken()
Promise.all([loadColumns(), loadIndexes()]).then(() => runSearch())
