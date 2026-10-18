import { readFileSync } from 'node:fs'
import { createConnection } from 'mysql2/promise'

const url = process.env.WORDS_DATABASE_URL
if (!url) {
  console.error('WORDS_DATABASE_URL is not set')
  process.exit(1)
}

const args = process.argv.slice(2)
if (args[0] === '--expect-absent') {
  const names = args.slice(1)
  if (names.length === 0) {
    console.error('usage: node scripts/apply-words-sql.mjs --expect-absent <table>...')
    process.exit(1)
  }
  const conn = await createConnection(url)
  try {
    const placeholders = names.map(() => '?').join(', ')
    const [rows] = await conn.query(
      `SELECT table_name AS name
       FROM information_schema.tables
       WHERE table_schema = DATABASE()
         AND table_name IN (${placeholders})`,
      names
    )
    const found = rows.map(row => row.name)
    if (found.length > 0) {
      console.error(`expected tables to be absent, still present: ${found.join(', ')}`)
      process.exit(1)
    }
    console.log(`absent: ${names.join(', ')}`)
  } finally {
    await conn.end()
  }
  process.exit(0)
}

const file = args[0]
if (!file) {
  console.error('usage: WORDS_DATABASE_URL=... node scripts/apply-words-sql.mjs <sql-file>')
  process.exit(1)
}

const statements = readFileSync(file, 'utf8')
  .split('\n')
  .filter(line => !line.trim().startsWith('--'))
  .join('\n')
  .split(';')
  .map(statement => statement.trim())
  .filter(Boolean)

const conn = await createConnection(url)
try {
  for (const statement of statements) {
    await conn.query(statement)
  }
  console.log(`applied ${statements.length} statement(s) from ${file}`)
} finally {
  await conn.end()
}
