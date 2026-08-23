import type { ApiRiskLevel, CoolSpot, RouteId, SpotFilter } from './types'

export type Language = 'en' | 'ja'

interface UiCopy {
  header: { title: string; subtitle: string; waiting: string; switchLanguage: string }
  status: {
    loading: string
    current: string
    unavailable: string
    unavailableHelp: string
    tokyoNow: string
    observed: string
    measured: string
    estimated: string
  }
  guidance: Record<ApiRiskLevel, { title: string; detail: string }>
  risk: {
    official: string
    title: string
    about: string
    aboutTitle: string
    labels: Record<ApiRiskLevel, string>
  }
  location: {
    explore: string
    title: string
    pointA: string
    notSet: string
    destination: string
    selectPlace: string
    locating: string
    useLocation: string
    demo: string
  }
  categories: Record<CoolSpot['category'], { label: string; detail: string }>
  filters: Record<SpotFilter, string>
  map: {
    aria: string
    legendAria: string
    yourLocation: string
    park: string
    water: string
    indoor: string
    route: string
  }
  emptyMap: { eyebrow: string; title: string; detail: string }
  selection: { eyebrow: string; away: string; about: string; minuteWalk: string }
  routes: {
    compare: string
    calculating: string
    alternativesAria: string
    bestBalance: string
    labels: Record<RouteId, string>
    minutes: string
    exposed: string
  }
  spots: {
    within: string
    title: string
    filterAria: string
    emptyTitle: string
    emptyDetail: string
    noneTitle: string
    noneDetail: string
    footer: string
  }
  errors: {
    generic: string
    retry: string
    unsupportedLocation: string
    permissionDenied: string
    locationFailed: string
  }
  methodNote: string
}

export const UI_COPY: Record<Language, UiCopy> = {
  en: {
    header: {
      title: 'Tokyo Cool Route',
      subtitle: 'Heat-safe walking support',
      waiting: 'Waiting for WBGT',
      switchLanguage: '日本語に切り替える',
    },
    status: {
      loading: 'Loading current WBGT',
      current: 'Current conditions',
      unavailable: 'WBGT unavailable',
      unavailableHelp: 'Run WBGT_Monitor.py, then refresh this page.',
      tokyoNow: 'Tokyo right now',
      observed: 'Observed',
      measured: 'measured',
      estimated: 'estimated',
    },
    guidance: {
      'Almost Safe': {
        title: 'Heat risk is currently low',
        detail: 'Stay hydrated and check conditions again before a longer trip.',
      },
      Caution: {
        title: 'Hydrate before you leave',
        detail: 'Take breaks in shade, especially during physical activity.',
      },
      Warning: {
        title: 'Plan regular cooling breaks',
        detail: 'Avoid strenuous activity and use shaded streets where possible.',
      },
      'Severe Warning': {
        title: 'Avoid outdoor activity if possible',
        detail: 'If travel is essential, keep it short and stop in cool indoor places.',
      },
      Danger: {
        title: 'Avoid going outside now',
        detail: 'Stay in an air-conditioned place and delay non-essential travel.',
      },
    },
    risk: {
      official: 'Official scale',
      title: 'WBGT risk level',
      about: 'About WBGT',
      aboutTitle: 'WBGT is the Wet Bulb Globe Temperature',
      labels: {
        'Almost Safe': 'Almost Safe',
        Caution: 'Caution',
        Warning: 'Warning',
        'Severe Warning': 'Severe Warning',
        Danger: 'Danger',
      },
    },
    location: {
      explore: 'Explore nearby',
      title: 'Choose your location',
      pointA: 'Point A',
      notSet: 'Not set',
      destination: 'Cool destination',
      selectPlace: 'Select a place on the map',
      locating: 'Finding your location…',
      useLocation: 'Use my location',
      demo: 'Try Shinjuku demo',
    },
    categories: {
      Park: { label: 'Park', detail: 'Outdoor shade' },
      'Drinking Station': { label: 'Water', detail: 'Hydration point' },
      'Convenience Store': { label: 'Konbini', detail: 'Air-conditioned convenience store' },
    },
    filters: { All: 'All', Indoor: 'Konbini', Parks: 'Parks', Water: 'Water' },
    map: {
      aria: 'Map of nearby cooling places',
      legendAria: 'Map legend',
      yourLocation: 'Your location',
      park: 'Park',
      water: 'Drinking water',
      indoor: 'Konbini',
      route: 'Walking route',
    },
    emptyMap: {
      eyebrow: 'Start here',
      title: 'Find relief from the heat nearby',
      detail: 'Use your current location to see parks, drinking water, and nearby konbini.',
    },
    selection: {
      eyebrow: 'Selected cool spot',
      away: 'm away',
      about: 'about',
      minuteWalk: 'min walk',
    },
    routes: {
      compare: 'Compare walking routes',
      calculating: 'Calculating routes…',
      alternativesAria: 'Walking route alternatives',
      bestBalance: 'Best balance',
      labels: { shortest: 'Fastest', coolest: 'Coolest', balanced: 'Recommended' },
      minutes: 'min',
      exposed: 'exposed',
    },
    spots: {
      within: 'Within 1.2 km',
      title: 'Nearby cool spots',
      filterAria: 'Filter cooling places',
      emptyTitle: 'Your nearby places will appear here',
      emptyDetail: 'Share your location or use the demo point to explore the interface.',
      noneTitle: 'No matching places found',
      noneDetail: 'Choose another category or try a different location.',
      footer: 'Availability and opening hours should be confirmed before travel.',
    },
    errors: {
      generic: 'An unexpected error occurred',
      retry: 'Retry',
      unsupportedLocation: 'This browser does not support location access.',
      permissionDenied: 'Location permission was denied. Use the Shinjuku demo or enable location access.',
      locationFailed: 'Your location could not be determined. Please try again.',
    },
    methodNote: 'Official WBGT guidance · Cool-place ranking is an estimate based on category and distance.',
  },
  ja: {
    header: {
      title: '東京クールルート',
      subtitle: '暑さを避ける徒歩移動サポート',
      waiting: 'WBGTを取得中',
      switchLanguage: 'Switch to English',
    },
    status: {
      loading: '現在のWBGTを読み込んでいます',
      current: '現在の状況',
      unavailable: 'WBGTを取得できません',
      unavailableHelp: 'WBGT_Monitor.pyを実行してから、ページを更新してください。',
      tokyoNow: '現在の東京',
      observed: '観測時刻',
      measured: '実測値',
      estimated: '推定値',
    },
    guidance: {
      'Almost Safe': {
        title: '現在の暑さリスクは低めです',
        detail: '水分を補給し、長時間の外出前にもう一度状況を確認しましょう。',
      },
      Caution: {
        title: '出発前に水分を補給しましょう',
        detail: '運動時は特に、日陰でこまめに休憩してください。',
      },
      Warning: {
        title: '定期的な涼しい場所での休憩を計画しましょう',
        detail: '激しい運動を避け、できるだけ日陰の道を利用してください。',
      },
      'Severe Warning': {
        title: '可能であれば屋外活動を避けてください',
        detail: '外出が必要な場合は短時間にし、涼しい屋内施設で休憩してください。',
      },
      Danger: {
        title: '今は外出を避けてください',
        detail: '冷房のある場所で過ごし、不要不急の外出を延期してください。',
      },
    },
    risk: {
      official: '公式基準',
      title: 'WBGT危険度',
      about: 'WBGTとは',
      aboutTitle: 'WBGTは暑さ指数（湿球黒球温度）です',
      labels: {
        'Almost Safe': 'ほぼ安全',
        Caution: '注意',
        Warning: '警戒',
        'Severe Warning': '厳重警戒',
        Danger: '危険',
      },
    },
    location: {
      explore: '周辺を探す',
      title: '現在地を選択',
      pointA: '出発地点 A',
      notSet: '未設定',
      destination: '涼しい目的地',
      selectPlace: '地図から場所を選択',
      locating: '現在地を取得中…',
      useLocation: '現在地を使用',
      demo: '新宿デモを試す',
    },
    categories: {
      Park: { label: '公園', detail: '屋外の日陰' },
      'Drinking Station': { label: '給水', detail: '給水スポット' },
      'Convenience Store': { label: 'コンビニ', detail: '冷房のあるコンビニ' },
    },
    filters: { All: 'すべて', Indoor: 'コンビニ', Parks: '公園', Water: '給水' },
    map: {
      aria: '周辺の涼しい場所の地図',
      legendAria: '地図の凡例',
      yourLocation: '現在地',
      park: '公園',
      water: '給水スポット',
      indoor: 'コンビニ',
      route: '徒歩ルート',
    },
    emptyMap: {
      eyebrow: 'ここから開始',
      title: '近くの涼しい場所を探す',
      detail: '現在地を使用して、公園、給水スポット、近くのコンビニを表示します。',
    },
    selection: {
      eyebrow: '選択中の涼しい場所',
      away: 'm先',
      about: '約',
      minuteWalk: '分',
    },
    routes: {
      compare: '徒歩ルートを比較',
      calculating: 'ルートを計算中…',
      alternativesAria: '徒歩ルートの候補',
      bestBalance: 'バランス重視',
      labels: { shortest: '最短', coolest: '涼しさ優先', balanced: 'おすすめ' },
      minutes: '分',
      exposed: '暑さにさらされる区間',
    },
    spots: {
      within: '1.2 km以内',
      title: '近くの涼しい場所',
      filterAria: '涼しい場所を絞り込む',
      emptyTitle: '近くの場所がここに表示されます',
      emptyDetail: '現在地を共有するか、新宿デモを使用してください。',
      noneTitle: '該当する場所がありません',
      noneDetail: '別のカテゴリまたは場所をお試しください。',
      footer: '利用状況や営業時間は、出発前に確認してください。',
    },
    errors: {
      generic: '予期しないエラーが発生しました',
      retry: '再試行',
      unsupportedLocation: 'このブラウザは位置情報に対応していません。',
      permissionDenied: '位置情報の使用が許可されていません。設定を有効にするか、新宿デモをお試しください。',
      locationFailed: '現在地を取得できませんでした。もう一度お試しください。',
    },
    methodNote: '環境省のWBGT基準を使用 · 涼しい場所の順位はカテゴリと距離に基づく推定です。',
  },
}
