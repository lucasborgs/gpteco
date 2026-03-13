export interface MusicaItem {
  artista: string
  musica: string
  pedidos: number
}

export interface TendenciaItem {
  posicao: number
  artista: string
  musica: string
  pedidos: number
  tendencia: 'up' | 'down' | 'same' | 'new'
}

export interface DiaSemanaItem {
  dia_semana: number
  dia_nome: string
  pedidos: number
}

export interface HeatmapItem {
  hora: number
  dia_semana: number
  pedidos: number
}

export interface TaxaAtendimento {
  total: number
  sucesso: number
  recusado: number
  taxa_sucesso_pct: number
  por_motivo: Record<string, number>
}

export interface OuvinteEngajado {
  numero_mascarado: string
  pedidos: number
  primeiro_pedido: string
}

export interface DDDItem {
  ddd: string
  pedidos: number
}

export interface ArtistaItem {
  artista: string
  pedidos: number
}

export interface AnalyticsData {
  top_musicas_all_time: MusicaItem[]
  top_musicas_semana: MusicaItem[]
  tendencia_musicas: TendenciaItem[]
  pico_por_dia_semana: DiaSemanaItem[]
  heatmap_pedidos: HeatmapItem[]
  taxa_atendimento: TaxaAtendimento
  ouvintes_engajados: OuvinteEngajado[]
  breakdown_ddd: DDDItem[]
  top_artistas: ArtistaItem[]
}
