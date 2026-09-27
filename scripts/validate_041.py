import re, json

t = open('content/queue/041-prompt-injection.json').read()
d = json.loads(t)

# JP/CN check
jp = re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', t)
print('JP/CN check:', 'OK' if not jp else 'FAIL: ' + str(jp))

# Card count
print('Cards:', len(d['cards']), '(min 5, max 10)')

# Visual card check
for i, c in enumerate(d['cards']):
    if c.get('type') == 'visual':
        heading = bool(c.get('heading'))
        visual = bool(c.get('visual'))
        caption = bool(c.get('caption'))
        print(f'Card {i+1} (visual): heading={heading}, visual={visual}, caption={caption}')

# Structure check (required fields)
print('Topic:', d.get('topic', 'MISSING'))
print('Caption:', bool(d.get('caption')))
print('Hashtags:', len(d.get('hashtags', [])))

# Check for empty cards
for i, c in enumerate(d['cards']):
    if 'body' in c and not c['body'].strip():
        print('WARN: Card', i+1, 'has empty body')