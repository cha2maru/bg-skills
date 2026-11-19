---
type: functional-contract
id: CTR-F-001
revision: 3
title: ゲーム定義の形式（bg-def）
provider: /structure/CMP-0101.md
format: file-format
thickness: thick
elements: [ゲーム定義, シナリオ]
external_users: [ゲーム設計者（人の手）, エージェント（定義を書く・読む）]
status: stable
tags: [concept]
implementation: []
---

# CTR-F-001：ゲーム定義の形式（bg-def）

プロダクトの中心の契約。エージェントが不足なく読めるゲームの定義（RUL-001 #25・#28）を、概念の形として定める。


## 形式の正本（r2）

項目の名前と置き場所の正本は `src/bgskills/schema.py`（FIELDS）。`bg check` は形式に無い項目を似た項目つきで指摘し、`bg schema` は JSON Schema を書き出す。この文書の表は値の意味の説明で、名前が食い違えば schema.py が正しい。r2 からは確定（stable）なので、項目を足すときも版を上げる（RUL-016：作品ごとに形式を膨らませない）。

## Concept Model

定義に現れるものは、できる限り 2 つの物の原型（エリアとオブジェクト）の派生として表す。派生で表せないものだけを、別の原型として持つ（RUL-005 #2）。原型は次の 8 つ。

| 原型 | 区分 | 何か | 派生で表せない理由 |
|---|---|---|---|
| エリア（area） | 物 | 物を置く場所。入れ子・位置（pos・xy）・公開範囲・順番・上限・入ったときの状態・持ち主を持つ | — |
| オブジェクト（object） | 物 | 置かれる物。種類・状態（値ごとの表示方法）・属性・持ち主・数量（区別しない部品）を持ち、上に物を載せられる（物の置き場にもなる） | — |
| リンク（link） | 関係 | 2 つ以上のエリアのつながり（種類つき） | 物ではなく、物と物の間の関係 |
| プレイヤー（player） | 主体 | 操作を行う立場（人・エージェント・オートマ）。席はエリアで表す | 物ではなく、操作の主語 |
| ルール・用語（rule・term） | 文 | 自然文の正本と、その中の言葉 | 局面にない。ルールの中身は機械化しない（RUL-001 #31） |
| 操作（op） | 変化 | 局面を変える最小の単位（move・attach・set・shuffle・roll・spread・advance・progress・say・end など） | 物ではなく、時間の中の出来事 |
| 式（expr） | 読み | 局面を読んで値を出す（決まった関数だけ） | 物ではなく、物の読み方 |
| 進行（flow） | 時間 | 段階・手番・フェーズ・周回と、アクションの区分・回数 | 物ではなく、時間の区切り |

### 派生の一覧（原型からの組み立て）

| 定義に現れるもの | 派生のしかた | 例 |
|---|---|---|
| 盤・マス・山・手札・捨て札・火・駒台・河・王牌・六角の交点と辺 | エリアの種類（`kinds.<id>.base: area`） | かがり火の火、カタンの交点、将棋の駒台、麻雀の河 |
| カード・駒・石・牌・コマ・トークン・ダイス・タイル・カウンター | オブジェクトの種類（`base: object`） | 将棋の駒（向き＝状態 side、成り＝状態 status の裏返し）、オセロの石（色＝状態） |
| 場所の性質（港など） | オブジェクトの種類に `fixture: true`（空き・上限に数えない） | カタンの港 |
| 資源などの区別しない部品 | オブジェクトに数量（`count`） | カタンの資源、惨劇RoopeR の不安・暗躍 |
| 卓・箱 | エリア（卓は根のエリア、`table` はその配置の略記。箱は既定のエリア） | — |
| 席・プレイヤーエリア | エリア（`owner` つき） | かがり火の player-P1 |
| 組（3 つ並びなど） | リンクの派生（n 個のエリアのつながり。`groups` はその略記） | 三目並べの line |
| 盤の向きと隣 | エリアの位置（pos）から式で導く（step・ray）。六角の 6 方向はリンク | チェスの走り、オセロの挟み |
| 進行の状態（手番のプレイヤー・フェーズ・記憶） | 「ゲーム」というオブジェクトの状態（`progress` はその略記） | 惨劇RoopeR の前のループの友好 |
| 指標・知らせ・終了の条件・条件の名前 | 用語に式を付けたもの（名前つきの式） | 最長交易路、事件の条件 |
| アクション | 操作の並び（引数・条件・繰り返し・分岐） | 産出、行動の解決 |
| オートマ | プレイヤーの席の着席者 | — |
| シナリオ（脚本） | 定義に重ねる非公開の部分（定義の外の概念） | 惨劇RoopeR の配役 |
| トラック（日・ループ・得点の列） | 盤のエリアと、列のマスの子のエリア（rect で絵の上の位置）と、目印のオブジェクト。目印を進行に合わせて動かすのは進行の on_start（エリアの on_enter の時間版） | 惨劇RoopeR のデータボード |
| 画像（背景・表・裏の絵） | 原型の表示方法（image・back_image。状態で替わる絵は状態の表示方法と同じ考え） | 惨劇RoopeR のボード・キャラクター（死体の絵）・行動カードの裏 |
| 発言（全員・内緒話） | 操作の派生（say。物を変えず、話したことを残す。to で聞かせる相手。中身の真偽は見ない） | 人狼の議論、ディプロマシーの密談 |
| 話せる・話せない時間 | 進行の段階・フェーズの talk（真偽か式。speaker・to） | 花火（ヒントだけ）、人狼の夜（人狼どうしだけ）、ディプロマシーの命令中 |
| 割り込み（スタック・キュー） | 操作の派生（アクションの stack: true で解決待ちの列に積む。pass で見送り、積んだ人以外が見送ったら解決。cancel で打ち消し。flow.stack: fifo でキュー） | 呪文と打ち消し（tests/test_stack.py） |
| 提案と合意（守られる約束） | 発言の派生（say の offer：受けたらまとめて行う操作。answer で受ける・断る・取り下げ、reply_to で条件を変えて返す） | カタンのプレイヤー間の交換 |
| 決まった形の発言 | アクション（手順に say と know の fields） | 花火のヒント |
| 紙に書く値（命令書・投票用紙） | オブジェクトの状態を型（text・player・area・number）で書く（書き込む状態） | ディプロマシーの命令、人狼の投票先 |
| 封をした選択（伏せて書いて一斉に開く） | 書き込む状態を持つオブジェクトを、伏せる（表裏の状態か、持ち主だけに見えるエリア）→ 一斉に表にするアクション | ディプロマシーの命令、人狼の投票 |
| 自分だけ見えない手札 | エリアの公開範囲 others（持ち主以外に見える） | 花火 |
| 一部だけの知識 | 操作 know の fields（その項目だけを知る） | 花火のヒント、人狼の占い（陣営だけ） |
| 隠れた役職 | 持ち主だけに見えるエリアに伏せたカード＋ know（仲間を知る） | 人狼 |
| 非公開の行為 | アクションの secret（ほかの人の記録では中身も相手も伏せる） | 人狼の夜の行動 |
| カードの効果（ワザ・トレーナー） | アクション（効果の語彙は定義の if で書く。結果を読む効果は stepwise） | 精霊獣デュエルのワザ・きずぐすり |
| ステータス（HP・タイプ・弱点） | オブジェクトの属性。受けたダメージは上に重ねる数の部品（ダメージカウンター）、状態異常は状態 | 精霊獣デュエル |
| 地図（絵のない盤） | 根のエリアの子に rect か poly（多角形。形は表示方法で、隣接はリンクが正）、親に aspect。つながりはリンク（種類で陸・海を分ける）。海岸が 2 つの州は子のエリア | ディプロマシー |
| プレイヤーの色 | プレイヤーの表示方法（color。持ち主のある部品を塗る） | ディプロマシーの国の色 |

### 派生に寄せきれていないもの（実装と形式の差）

| もの | 今の形式 | 寄せる先 | 扱い |
|---|---|---|---|
| progress | トップレベルのキー | 「ゲーム」オブジェクトの状態 | 略記として残す。意味は状態と同じ（形式 0.2 で `objects` の game の states にも書けるようにする候補） |
| groups | トップレベルのキー | リンク（n 個） | 略記として残す |
| metrics・flow.signals・flow.end_when | 別々のキー | 用語＋式（名前つきの式） | 略記として残す。引数を持つ名前つきの式は functions（SPC-066）で、どの式からも呼べる |
| table | トップレベルのキー | 根のエリアの配置 | 略記として残す |

## Parties

| 立場 | システム・開発オブジェクト | 責任者 |
|---|---|---|
| 提供 | CMP-0101 定義（OBJ-010101 読み込みと展開、OBJ-010102 定義のトレーナー） | 記載なし |
| 利用 | OBJ-010201 局面と操作、OBJ-010401 bg コマンド、OBJ-010801 定義づくりのスキル、人・エージェント | 記載なし |

## Files and Placement

- ゲーム定義：1 ゲーム 1 ファイルの YAML（UTF-8）。公開してよいものは `examples/`、既存の商用ゲームは `local/`（公開しない。RUL-001 #37）
- シナリオ：対局ごとの非公開の部分（配役など）。別の YAML。対局を作るときに渡し、対局のフォルダに写す

## Structure

トップレベルのキー（`format: bg-def/0.1`）。キーは英語、中身（name・text）は日本語。

## Fields

| キー | 型 | 必須 | 値 | 意味（原型との関係） |
|---|---|---|---|---|
| format | 文字列 | ○ | bg-def/0.1 | 形式の版 |
| assets | 辞書 | | root（画像の置き場。定義のファイルからの相対パス）・credit（画像の表記） | 表示の画像の置き場（RUL-006） |
| game | 辞書 | ○ | id・name・summary・version・players{min,max}・open_questions・strict（対局の既定を厳格モードにする。bg new --lenient で外せる） | ゲームの見出しと未決 |
| players | 並び | ○ | id・name・text・color（for_each・copies 可） | 原型：プレイヤー |
| kinds | 辞書 | | base（area・object・ほかの種類）・text・name・states（値ごとに text と show{rotate,face}。値の並びの代わりに型 text・player・area・number を書くと書き込む状態）・show_state（いつも出す項目）・derived（部品ごとに局面から計算して見え方に出す値。式の self が部品。残り HP など）・attributes・capacity・ordered・fixture・uses・image・back_image・shape（round） | 種類。必ず area か object にたどり着く |
| areas | 並び | ○ | id・kind・name・owner・visibility{exists,count,face,order。値は all・owner・others・none・席の並び}・ordered・capacity・on_enter・areas（入れ子）・layout{grid・hex}・pos・xy・rect（親の中の [x, y, 幅, 高さ] の割合）・poly（親の中の多角形の頂点の割合。複雑な形）・color（塗り）・aspect（絵のないときの縦横比）・image（背景）・folded（画面で最初にたたむ） | 原型：エリア |
| objects | 並び | | id・kind・count・copies・for_each・attributes・owner・start・start_state・image・back_image（文字列か {default, "状態=値"}） | 原型：オブジェクト |
| links | 並び | | between・type | 原型：リンク |
| groups | 辞書 | | members | リンクの派生（略記） |
| table | 辞書 | | center・per_player | 根のエリアの配置（略記） |
| progress | 辞書 | | text・start | ゲームの状態（略記） |
| actions | 並び | | id・name・rule・when・by・secret・stack（解決待ちに積む）・cost（積むときにすぐ行う手順：払う・唱えている場所へ）・during_stack（スタックがあっても行える）・stepwise（手順ごとに局面を更新し、続く式が結果を読む）・params（in・from・kind・owner・players・choices・free・require・pick）・require・let・steps（op・let・each・if・call：ほかのアクションの手順を args で呼ぶ） | 操作の並び |
| flow | 辞書 | | stages（on_start・talk・talk_text・whisper：hidden なら内緒話はあったことも見せない）・turns（on_start：手順を 1 つずつ行い、後の式は結果を読む、on_end：手番が替わる前に行う手順（手札の上限など）、phases：main・max・each（メインアクションごとの回数）・per_player・sequence・required・auto・pass・by・talk、free（max・phases：行えるフェーズ）・reactions）・cycle・end_when（expr・text・winners・losers・draw・winners: scoring・timing：now・turn_end・round_end。並びが優先）・auto_end（満たしたら結果を記録して終える）・scoring（by・tiebreak・low）・signals（public：プレイヤーにも出す）・offer_action（提案が成立したら出した人が行ったことにするアクション）・stack（fifo ならキュー） | 原型：進行 |
| metrics | 並び | | id・per・count・expr・needs・visible・badge | 名前つきの式 |
| functions | 対応表 | | 名前 → params・expr | 名前つきの式（引数を持つ。どの式からも 名前(引数) で呼ぶ） |
| terms | 辞書 | | word・text・refs | 原型：用語 |
| rulings | 並び | | id・question・decision・reason・rules・refs・principle・status（decided・open）・authority（official・author・designer・keeper）・by・date・sources・found_in・supersedes・engine | ルールの派生：文で決まらない点（ルールの穴）を決める裁定（RUL-017） |
| rules | 並び | ○ | id・type・text・refs | 原型：ルール（正本） |

## Validation Rules

- 誤り（読み込みを止める）：YAML として読めない、人数が範囲外、ID の重複（種類をまたいで一意）
- 参照の確認（bg check）：ルール・用語・アクション・指標・進行・卓の参照先がない、種類の base が area・object にたどり着かない、式（expr・if・each・let・talk・functions）が読めない・知らない関数を呼ぶ・文字列で書いた名前（progress・metric の鍵、state・attr・where の部品）が定義にない
- 警告（読み込みは続ける）：上限を超える置き場、進行から外れた行為（厳格モードでは拒否）

## Example

`examples/tic-tac-toe.yaml`（最小）、`examples/kagaribi.yaml`（カード）、`examples/hex-skirmish.yaml`（六角）、`examples/othello.yaml`・`chess.yaml`・`shogi.yaml`・`mahjong.yaml`（古典。RUL-005 #1）、`examples/werewolf.yaml`（発言・隠れた役職・投票。RUL-009）、`examples/beast-duel.yaml`（カードの効果・ステータス。RUL-011）。

## Compatibility

版は `format` に書く。キーを足すのは同じ版で行い、読む側は知らないキーを無視する。改名・削除は版を上げる。
