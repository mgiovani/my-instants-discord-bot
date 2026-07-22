.PHONY: test update-fixtures

UA := Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36
FETCH := curl -fsL --remove-on-error -A "$(UA)"

test:
	uv run pytest

update-fixtures:
	$(FETCH) "https://www.myinstants.com/search?name=discord" -o tests/fixtures/search_results.html
	$(FETCH) "https://www.myinstants.com/instant/discord-notification-38119/" -o tests/fixtures/instant_details.html
