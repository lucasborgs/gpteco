export interface MusicaItem {
  artista: string
  musica: string
  genero: string
  pedidos: number
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
  telefone_formatado: string
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

export interface GeneroItem {
  genero: string
  pedidos: number
}

export interface GeneroDetalhe {
  genero: string
  artista: string
  musica: string
  pedidos: number
}

export interface HeatmapDetalhe {
  hora: number
  dia_semana: number
  artista: string
  musica: string
  pedidos: number
}

export interface PedidoIndividual {
  artista: string
  musica: string
  genero: string
  numero: string
  data_pedido: string
  hora: number
  dia_semana: number
  sucesso: boolean
}

export interface VolumeDiaMes {
  dia: string
  pedidos: number
}

export interface AnalyticsData {
  top_musicas_all_time: MusicaItem[]
  pico_por_dia_semana: DiaSemanaItem[]
  heatmap_pedidos: HeatmapItem[]
  heatmap_detalhe: HeatmapDetalhe[]
  taxa_atendimento: TaxaAtendimento
  ouvintes_engajados: OuvinteEngajado[]
  breakdown_ddd: DDDItem[]
  top_artistas: ArtistaItem[]
  top_generos: GeneroItem[]
  generos_detalhe: GeneroDetalhe[]
  fas_frequentes: number
  pedidos_individuais: PedidoIndividual[]
  volume_dia_mes: VolumeDiaMes[]
}
