# レビュー（RUL-008）：見つけたことと判断

推奨案で進めた（人の確認をはさまない。RUL-004 の任せ方を引き継ぐ）。

## 直した不具合

| # | 症状 | 原因 | 直し方 | テスト |
|---|---|---|---|---|
| B1 | auto のフェーズでアクションの直後に undo すると、自動の advance だけが消え、アクションは残る。回数を使い切ったまま手番が戻り、そのフェーズで何もできなくなる（オセロで再現） | 自動の advance に action が付いていない | 自動の advance に action を付け、undo でアクションと一緒に外す | test_undo_takes_back_action_with_auto_advance |
| B2 | 席にない名前（P1 など）でも act・op が通り、記録に残る | 行う人を確かめていない | act・apply で、席か keeper でなければ受け付けない | test_unknown_actor_is_rejected |
| B3 | act の手順と pick: first の候補を、ロックの外で読んだ局面から作っていた（画面と同時に書くと古い局面の手順を記録しうる）。局面の再生も 1 回の act で 3 回 | 読む・足すの順 | ロックの中で 1 回だけ再生し、その局面から手順を作る | 既存のテスト |
| B4 | チェスの画面・局面（bg show）が開けない | 指標 material の式が .get を呼ぶ（式の言語では関数は名前で呼ぶ）。指標の式の誤りが view 全体を落とす | 指標を count の重み付きの sum で書き直す（式を使わない）。指標の式の誤りは値の欄に誤りを出し、局面は見られるようにする（end_signals と同じ扱い） | test_chess_material_and_view |
| B5 | 麻雀のチーが必ず失敗する | 上家を players().index で求めていた（メソッド呼び出し） | 式の関数 seat(player, k)（席の順で k 人先）を足し、seat(actor, -1) にする | test_mahjong_chi_takes_from_kamicha |

B4・B5 は、下の bg check の強化で見つかった。サンプルのテストは候補とアクションの一部だけを通っていて、指標と鳴きの片方を通っていなかった。

## 足した確認（bg check）

定義を書くエージェントが、対局の前に誤りに気づけるようにする（RUL-001 #25・#28：不足なく読める定義）。

- 式：actions・flow・metrics の expr・if・each・let の値を、計算せずに読み、使えない書き方と知らない関数を出す（{引数} は名前に置き換えて読む）
- 進行：段階の actions、フェーズの main、free・reactions のアクション、段階の turn、cycle の from・to
- 手順：each・if の do・else の中と、進行の on_start の手順も、置き場の参照を確かめる（each の as・let の名前は変数として見ない）

テスト：test_check_finds_exprs_flow_and_nested_steps。サンプル 7 つと local の 2 つは、直した後すべて missing_refs: []。

## 整理

- 定義を全体の変数（session._D）で渡していたのをやめ、引数で渡す（同じプロセスで複数の対局を開くと、別の定義で部品を選びうる）
- 部品の絞り込み（種類・持ち主・属性）を query._part_ok の 1 か所に寄せた（expr・metrics に同じものが 3 つあった。metrics の kind はリストも受けるようになった）。_under・_area_of の重複も 1 つに
- 誤りの受け方：OpError・DefinitionError・ExprError はすべて ValueError の派生なので、bg と画面の API は ValueError で受ける。画面の GET で式の誤りや知らないアクションが来ると、接続ごと落ちていた（400 で返すようにした）。bg candidates の知らないアクションは traceback だった

## 検討して見送ったもの

| 案 | 見送った理由 |
|---|---|
| 局面の再生のキャッシュ | 実測で、記録 430 操作（惨劇RoopeR）の再生 0.06 秒、表示 0.06 秒。画面の 1.5 秒ごとの読み直しに対して小さい。千操作を超える対局が出たら、記録の長さをキーに局面を持つ |
| 形式 0.2（略記 progress・groups・metrics を派生の書き方へ） | 破壊的な変更は許可されたが、既存の定義 9 つの書き換えに見合う不具合・読みにくさの報告がまだない。概念モデル（CTR-F-001）で略記と派生の対応は説明済み |
| apply_op の操作ごとの分岐を表に分ける | 長いが 1 か所で読め、操作を足す場所も明らか。分けても行数は減らない |
| advance の player（鳴き）で飛ばした手番の turn_no | 1 手番として数える今の扱いで、entered（買った手番には使えない）に支障がない。飛ばした人の手番を数える必要が出たら直す |
| 画面（ui.html）の全面の見直し | 画面の受入テスト 16 件が通り、今回のレビューで不具合の報告がない |
