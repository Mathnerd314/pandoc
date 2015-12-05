bullet_re = u'[\\*\u2022]|\\[[ \\*x]\\]|\d+\.|\w\.'
	# bullets can be '*' or 0x2022 for normal items
	# and '[ ]', '[*]' or '[x]' for checkbox items
	# and '1.', '10.', or 'a.' for numbered items (but not 'aa.')
_number_bullet_re = re.compile('^(\d+|\w)\.$')

parser_re = {
	'blockstart': re.compile("^(\t*''')\s*?\n", re.M),
	'pre':        re.compile("^(?P<escape>\t*''')\s*?(?P<content>^.*?)^(?P=escape)\s*\n", re.M | re.S),
	'splithead':  re.compile('^(==+[ \t]+\S.*?\n)', re.M),
	'heading':    re.compile("\A((==+)[ \t]+(.*?)([ \t]+==+)?[ \t]*\n?)\Z"),
	'splitlist':  re.compile("((?:^[ \t]*(?:%s)[ \t]+.*\n?)+)" % bullet_re, re.M),
	'listitem':   re.compile("^([ \t]*)(%s)[ \t]+(.*\n?)" % bullet_re),
	'unindented_line': re.compile('^\S', re.M),
	'indent':     re.compile('^(\t+)'),
    # Tags are identified by a leading @ sign
	'tag':        Re(r'(?<!\S)@(?P<name>\w+)\b', re.U),
	# All the experssions below will match the inner pair of
	# delimiters if there are more then two characters in a row.
	'link':     Re('\[\[(?!\[)(.+?)\]\]'),
	'img':      Re('\{\{(?!\{)(.+?)\}\}'),
	'emphasis': Re('//(?!/)(.+?)//'),
	'strong':   Re('\*\*(?!\*)(.+?)\*\*'),
	'mark':     Re('__(?!_)(.+?)__'),
	'sub':	    Re('_\{(?!~)(.+?)\}'),
	'sup':	    Re('\^\{(?!~)(.+?)\}'),
	'strike':   Re('~~(?!~)(.+?)~~'),
	'code':     Re("''(?!')(.+?)''"),
}

def _check_number_bullet(bullet):
	# if bullet is a numbered bullet this returns the number or letter,
	# None otherwise
	m = _number_bullet_re.match(bullet)
	if m:
		return m.group(1)
	else:
		return None


class Parser(ParserClass):

	def __init__(self, version=WIKI_FORMAT_VERSION):
		self.backward = version not in ('zim 0.26', WIKI_FORMAT_VERSION)

	def parse(self, input):
		# Read the file and divide into paragraphs on the fly.
		# Blocks of empty lines are also treated as paragraphs for now.
		# We also check for blockquotes here and avoid splitting them up.
		if isinstance(input, basestring):
			input = input.splitlines(True)

		paras = ['']
		def para_start():
			# This function is called when we suspect the start of a new paragraph.
			# Returns boolean for success
			if len(paras[-1]) == 0:
				return False
			blockmatch = parser_re['blockstart'].search(paras[-1])
			if blockmatch:
				quote = blockmatch.group()
				blockend = re.search('\n'+quote+'\s*\Z', paras[-1])
				if not blockend:
					# We are in a block that is not closed yet
					return False
			# Else append empty paragraph to start new para
			paras.append('')
			return True

		def blocks_closed():
			# This function checks if there are unfinished blocks in the last
			# paragraph.
			if len(paras[-1]) == 0:
				return True
			# Eliminate closed blocks
			nonblock = parser_re['pre'].split(paras[-1])
			#  Blocks are closed if none is opened at the end
			return parser_re['blockstart'].search(nonblock[-1]) == None

		para_isspace = False
		for line in input:
			# Try start new para when switching between text and empty lines or back
			if line.isspace() != para_isspace and blocks_closed():
				if para_start():
					para_isspace = line.isspace() # decide type of new para
			paras[-1] += line

		# Now all text is read, start wrapping it into a document tree.
		# Headings can still be in the middle of a para, so get them out.
		builder = TreeBuilder()
		builder.start('zim-tree')
		for para in paras:
			# HACK this char is recognized as line end by splitlines()
			# but not matched by \n in a regex. Hope there are no other
			# exceptions like it (crosses fingers)
			para = para.replace(u'\u2028', '\n')

			if self.backward and not para.isspace() \
			and not parser_re['unindented_line'].search(para):
				self._parse_block(builder, para)
			else:
				block_parts = parser_re['pre'].split(para)
				for i, b in enumerate(block_parts):
					if i % 3 == 0:
						# Text paragraph
						parts = parser_re['splithead'].split(b)
						for j, p in enumerate(parts):
							if j % 2:
								# odd elements in the list are headings after split
								self._parse_head(builder, p)
							elif len(p) > 0:
								self._parse_para(builder, p)
					elif i % 3 == 1:
						# Block
						self._parse_block(builder, b + '\n' + block_parts[i+1] + b + '\n')

		builder.end('zim-tree')
		return ParseTree(builder.close())

	def _parse_block(self, builder, block):
		'''Parse a block, like a verbatim paragraph'''
		if not self.backward:
			m = parser_re['pre'].match(block)
			if not m:
				logger.warn('Block does not match pre >>>\n%s<<<', block)
				builder.data(block)
			else:
				indent = self._determine_indent(block)
				block = m.group('content')
				if indent > 0:
					builder.start('pre', {'indent': indent})
					block = ''.join(
						map(lambda line: line[indent:], block.splitlines(True)))
				else:
					builder.start('pre')
				builder.data(block)
				builder.end('pre')
		else:
			builder.start('pre')
			builder.data(block)
			builder.end('pre')


	def _parse_head(self, builder, head):
		'''Parse a heading'''
		m = parser_re['heading'].match(head)
		assert m, 'Line does not match a heading: %s' % head
		level = 7 - min(6, len(m.group(2)))
		builder.start('h', {'level': level})
		builder.data(m.group(3))
		builder.end('h')
		builder.data('\n')

	def _parse_para(self, builder, para):
		'''Parse a normal paragraph'''
		if para.isspace():
			builder.data(para)
			return

		builder.start('p')

		parts = parser_re['splitlist'].split(para)
		for i, p in enumerate(parts):
			if i % 2:
				# odd elements in the list are lists after split
				self._parse_list(builder, p)
			elif len(p) > 0:
				# non-list part of the paragraph
				indent = 0
				for line in p.splitlines(True):
					# parse indenting per line...

					m = parser_re['indent'].match(line)
					if m: myindent = len(m.group(1))
					else: myindent = 0

					if myindent != indent:
						if indent > 0:
							builder.end('div')
						if myindent > 0:
							builder.start('div', {'indent': myindent})
						indent = myindent

					self._parse_text(builder, line[indent:])

				if indent > 0:
					builder.end('div')

		builder.end('p')

	def _determine_indent(self, text):
		lvl = 999 # arbitrary large value
		for line in text.splitlines():
			m = parser_re['indent'].match(line)
			if m:
				lvl = min(lvl, len(m.group(1)))
			else:
				return 0
		return lvl

	def _parse_list(self, builder, list):
		'''Parse a bullet list'''

		indent = self._determine_indent(list)
		lines = list.splitlines()
		if indent > 0:
			lines = [line[indent:] for line in lines]
			self._parse_sublist(builder, lines, 0, attrib={'indent': indent})
		else:
			self._parse_sublist(builder, lines, 0)

	def _parse_sublist(self, builder, lines, level, attrib=None):
		listtype = None
		first = True
		while lines:
			line = lines[0]
			m = parser_re['listitem'].match(line)
			assert m, 'Line does not match a list item: >>%s<<' % line
			prefix, bullet, text = m.groups()

			if first:
				number = _check_number_bullet(bullet)
				if number:
					listtype = 'ol'
					if not attrib:
						attrib = {}
					attrib['start'] = number
				else:
					listtype = 'ul'
				builder.start(listtype, attrib)
				first = False

			mylevel = prefix.replace(' '*TABSTOP, '\t').count('\t')
			if mylevel > level:
				self._parse_sublist(builder, lines, level+1) # recurs
			elif mylevel < level:
				builder.end(listtype)
				return
			else:
				if listtype == 'ol':
					attrib = None
				elif bullet in bullets: # ul
					attrib = {'bullet': bullets[bullet]}
				else: # ul
					attrib = {'bullet': '*'}
				builder.start('li', attrib)
				self._parse_text(builder, text)
				builder.end('li')

				lines.pop(0)

		builder.end(listtype)

	def _parse_text(self, builder, text):
		'''Parse a piece of rich text, handles all inline formatting'''
		list = [text]
		list = parser_re['code'].sublist(
				lambda match: ('code', {}, match[1]), list)

		def parse_link(match):
			parts = match[1].strip('|').split('|', 2)
				# strip "|" to check against bugs like [[|foo]] and [[foo|]]
			link = parts[0]
			if len(parts) > 1:
				mytext = parts[1]
			else:
				mytext = link
			return ('link', {'href':link}, mytext)

		list = parser_re['link'].sublist(parse_link, list)

		def parse_image(match):
			parts = match[1].split('|', 2)
			src = parts[0]
			if len(parts) > 1: mytext = parts[1]
			else: mytext = None
			attrib = self.parse_image_url(src)
			return ('img', attrib, mytext)

		list = parser_re['img'].sublist(parse_image, list)


		# Put URLs here because urls can appear in links or image tags, but other markup
		# can appear in links, like '//' or '__'
		list = url_re.sublist(
				lambda match: ('link', {'href':match[1]}, match[1]) , list)

		for style in 'strong', 'mark', 'strike','sub', 'sup':
			list = parser_re[style].sublist(
					lambda match: (style, {}, match[1]) , list)

		for style in 'emphasis',:
			list = parser_re[style].sublist(
					lambda match: (style, {}, match[1]) , list)

		def parse_tag(re_):
			groups = re_.m.groupdict()
			return ('tag', groups, "@%s" % groups["name"])

		list = parser_re['tag'].sublist(parse_tag, list)

		for item in list:
			if isinstance(item, tuple):
				tag, attrib, text = item
				builder.start(tag, attrib)
				if text:
					builder.data(text)
				builder.end(tag)
			else:
				builder.data(item)

class Parser(ParserClass):

	# TODO parse constructs like *bold* and /italic/ same as in email,
	# but do not remove the "*" and "/", just display text 1:1

	# TODO also try at least to parse bullet and checkbox lists
	# common base class with wiki format

	# TODO parse markdown style headers

	def parse(self, input):
		if isinstance(input, basestring):
			input = input.splitlines(True)

		input = url_re.sublist(
			lambda match: ('link', {'href':match[1]}, match[1]) , input)


		builder = TreeBuilder()
		builder.start('zim-tree')

		for item in input:
			if isinstance(item, tuple):
				tag, attrib, text = item
				builder.start(tag, attrib)
				builder.data(text)
				builder.end(tag)
			else:
				builder.data(item)

		builder.end('zim-tree')
		return ParseTree(builder.close())


