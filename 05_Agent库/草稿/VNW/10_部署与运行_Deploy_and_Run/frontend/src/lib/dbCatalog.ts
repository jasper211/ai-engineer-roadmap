export interface DbCatalogColumn {
  name: string
  type: string
}

export interface DbCatalogTable {
  schema: string
  table: string
  row_count: number
  columns: DbCatalogColumn[]
  role: '流程数据' | '业务数据' | '系统数据'
  description: string | null
}

export interface DbCatalog {
  schema_version: string
  source_policy: string
  schemas: string[]
  tables: DbCatalogTable[]
}

export async function loadDbCatalog(): Promise<DbCatalog> {
  const response = await fetch('/data/db_catalog.json')
  if (!response.ok) throw new Error('数据库目录读取失败')
  return response.json()
}
