import { useState } from 'react'
import { Send, ChevronDown, ChevronRight } from 'lucide-react'
import { queryNLQ } from '../../api'
import type { NLQResult } from '../../types'
import { ChartRenderer } from '../ChartRenderer'

interface Props { clientId: number }

const EXAMPLES = [
  'Which channel has the highest publish rate?',
  'Show me monthly output trend for the last 6 months',
  'Which input type generates the most published outputs?',
  'Top 10 users by outputs created',
  'Compare publish rate across languages',
]

export function NLQTab({ clientId }: Props) {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<NLQResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [showSql, setShowSql] = useState(false)

  const submit = async (q?: string) => {
    const text = (q ?? question).trim()
    if (!text) return
    setQuestion(text)
    setLoading(true)
    setResult(null)
    setShowSql(false)
    try {
      const r = await queryNLQ(text, clientId)
      setResult(r)
    } catch (e) {
      setResult({
        question: text,
        error: String(e),
        sql: null,
        chart_type: 'table',
        title: 'Error',
        x: '', y: '',
        description: '',
        data: [],
        columns: [],
        row_count: 0,
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Input */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="font-semibold text-white mb-3">Ask anything about your analytics</h2>
        <div className="flex gap-3">
          <input
            type="text"
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
            placeholder="e.g. Which channel published the most videos last month?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            disabled={loading}
          />
          <button
            onClick={() => submit()}
            disabled={loading || !question.trim()}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            <Send className="w-4 h-4" />
            {loading ? 'Thinking…' : 'Ask'}
          </button>
        </div>

        {/* Example queries */}
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => submit(ex)}
              className="text-xs text-gray-400 bg-gray-800 hover:bg-gray-700 border border-gray-700 px-3 py-1.5 rounded-full transition-colors"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-center">
          <div className="inline-block w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin mb-3" />
          <p className="text-gray-400 text-sm">Generating SQL and fetching results…</p>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="space-y-4">
          {/* Error */}
          {result.error && (
            <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-red-400 text-sm">
              {result.error}
            </div>
          )}

          {/* Direct answer */}
          {!result.error && result.answer && (
            <div className="bg-gray-900 border border-gray-700 rounded-xl px-5 py-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Answer</p>
              <p className="text-gray-100 text-sm leading-relaxed">{result.answer}</p>
            </div>
          )}

          {/* Chart / table */}
          {!result.error && result.data.length > 0 && (
            <ChartRenderer spec={{
              chart_type: result.chart_type,
              title: result.title,
              description: result.description,
              data: result.data,
              x: result.x,
              y: result.y,
            }} />
          )}

          {!result.error && result.data.length === 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 text-gray-500 text-sm text-center">
              Query returned 0 rows.
            </div>
          )}

          {/* Generated SQL */}
          {result.sql && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <button
                onClick={() => setShowSql(v => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                <span className="font-medium">Generated SQL</span>
                {showSql ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
              {showSql && (
                <pre className="px-4 pb-4 text-xs text-green-400 overflow-x-auto font-mono leading-relaxed">
                  {result.sql}
                </pre>
              )}
            </div>
          )}

          {/* Row count */}
          {!result.error && (
            <p className="text-xs text-gray-500 text-right">{result.row_count} rows returned</p>
          )}
        </div>
      )}
    </div>
  )
}
