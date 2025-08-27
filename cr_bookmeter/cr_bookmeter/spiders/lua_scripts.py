# Splashを制御するための共通Luaスクリプト

BOOKMETER_LUA_SCRIPT = """
function main(splash, args)
  -- オプション: 広告やトラッキング用のドメインをブロックする
  local block_domains = {"google-analytics.com", "googletagmanager.com", "adservice.google.com"}
  splash:on_request(function(request)
    -- 画像リクエストを中止して高速化
    if request.resource_type == "image" then
      request.abort()
      return
    end
    -- 広告・トラッキングドメインへのリクエストを中止
    for _, domain in ipairs(block_domains) do
      if string.find(request.url, domain, 1, true) then
        request.abort()
        return
      end
    end
  end)

  -- ページのタイムアウトを長めに設定
  splash.resource_timeout = 20.0
  assert(splash:go(args.url))

  -- 書籍リストが表示されるまで最大10秒待機する (ポーリング処理)
  -- wait_for_elementが使えない環境向けの代替案
  if args.wait_for_selector then
    local wait_for_selector = args.wait_for_selector
    local attempts = 20  -- 最大試行回数 (20 * 0.5秒 = 10秒)
    local success = false
    for i = 1, attempts do
      local element_exists = splash:runjs(string.format(
          "document.querySelector('%s') !== null", wait_for_selector
      ))
      if element_exists then
        success = true
        break
      end
      splash:wait(0.5)
    end
    assert(success, "Timeout waiting for element: " .. wait_for_selector)
  end
  -- 念のため、要素表示後に少し待機
  splash:wait(0.5)

  return {
    html = splash:html()
  }
end
"""