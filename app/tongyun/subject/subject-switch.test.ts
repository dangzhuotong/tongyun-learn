import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SubjectSwitch from '@/components/tongyun/SubjectSwitch.vue'
import SelfGradePanel from '@/components/tongyun/SelfGradePanel.vue'
import type { Card } from './types'

async function render(component: unknown, props: Record<string, unknown> = {}): Promise<string> {
  return renderToString(createSSRApp(component as never, props))
}

describe('学科切换组件', () => {
  it('渲染出注册表里的全部学科选项', async () => {
    const html = await render(SubjectSwitch)
    expect(html).toContain('data-testid="subject-switch"')
    expect(html).toContain('value="java"')
    expect(html).toContain('value="ai"')
    expect(html).toContain('Java')
    expect(html).toContain('AI')
  })
})

describe('oral / project 自评 UI', () => {
  const card: Pick<Card, 'type' | 'rubric'> = {
    type: 'oral',
    rubric: ['要点一', '要点二', '要点三'],
  }

  it('展示 rubric 和三档自评按钮', async () => {
    const html = await render(SelfGradePanel, { card })
    expect(html).toContain('data-testid="self-grade"')
    expect(html).toContain('要点一')
    expect(html).toContain('要点二')
    expect(html).toContain('要点三')
    expect(html).toContain('data-testid="self-self_ok"')
    expect(html).toContain('data-testid="self-self_partial"')
    expect(html).toContain('data-testid="self-self_fail"')
    expect(html).toContain('不会')
  })
})
