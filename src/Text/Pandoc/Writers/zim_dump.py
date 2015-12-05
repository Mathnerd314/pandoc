WIKI_FORMAT_VERSION = 'zim 0.4'
info = {
	'name': 'wiki',
	'desc': 'Zim Wiki Format',
	'mimetype': 'text/x-zim-wiki',
	'extension': 'txt',
}
TABSTOP = 4
bullets = {
	'[ ]': UNCHECKED_BOX,
	'[x]': XCHECKED_BOX,
	'[*]': CHECKED_BOX,
	'*': BULLET,
}
bullet_types = {}
for bullet in bullets:
	bullet_types[bullets[bullet]] = bullet

class Dumper(DumperClass):
	def dump(self, tree):
		self.dump_children(tree.getroot(), output)

    def dump_children(self, list, output, list_level=-1, list_type=None, list_iter='0'):
		if list.text:
			output.append(list.text)

		for element in list.getchildren():
			if element.tag in ('p', 'div'):
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				self.dump_children(element, myoutput) # recurs
				if indent:
					myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'h':
				level = int(element.attrib['level'])
				if level < 1:   level = 1
				elif level > 5: level = 5
				## Markdown-style
				if level in (1, 2):
					# setext-style headers for lvl 1 & 2
					if level == 1: char = '='
					else: char = '-'
					heading = element.text
					line = char * len(heading)
					output.append(heading + '\n')
					output.append(line)
				else:
					# atx-style headers for deeper levels
					tag = '#' * level
					output.append(tag + ' ' + element.text)
                # zim-style
				tag = '='*(7 - level)
				output.append(tag+' '+element.text+' '+tag)
			elif element.tag in ('ul', 'ol'):
				indent = int(element.attrib.get('indent', 0))
				start = element.attrib.get('start')
				myoutput = TextBuffer()
				self.dump_children(element, myoutput, list_level=list_level+1, list_type=element.tag, list_iter=start) # recurs
				if indent:
					myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'li':
				if 'indent' in element.attrib:
					# HACK for raw trees from pageview
					list_level = int(element.attrib['indent'])
				if list_type == 'ol':
					bullet = str(list_iter) + '.'
					list_iter = increase_list_iter(list_iter) or '1' # fallback if iter not valid
				elif 'bullet' in element.attrib: # ul OR raw tree from pageview...
                    bullets = {
                        '[ ]': UNCHECKED_BOX,
                        '[x]': XCHECKED_BOX,
                        '[*]': CHECKED_BOX,
                        '*': BULLET,
                    }
                    bullet_types = reverse_map bullets
					if element.attrib['bullet'] in bullet_types:
						bullet = bullet_types[element.attrib['bullet']]
					else:
						bullet = element.attrib['bullet'] # Assume it is numbered..
				else: # ul
					bullet = '*'
				output.append('\t'*list_level+bullet+' ')
				self.dump_children(element, output, list_level=list_level) # recurs
				output.append('\n')
			elif element.tag == 'pre':
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				myoutput.append("'''\n"+element.text+"'''\n")
				if indent:
					myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'img':
				src = element.attrib['src']
				opts = []
				items = element.attrib.items()
				# we sort params only because unit tests don't like random output (i.e., don't bother)
				items.sort()
				for k, v in items:
					if k == 'src' or k.startswith('_'):
						continue
					elif v: # skip None, "" and 0 (optional
						opts.append('%s=%s' % (k, v))
				if opts:
					src += '?%s' % '&'.join(opts)

				if element.text:
					output.append('{{'+src+'|'+element.text+'}}')
				else:
					output.append('{{'+src+'}}')

			elif element.tag == 'sub':
				output.append("_{%s}" % element.text)
			elif element.tag == 'sup':
				output.append("^{%s}" % element.text)
			elif element.tag == 'link':
				assert 'href' in element.attrib, \
					'BUG: link %s "%s"' % (element.attrib, element.text)
				href = element.attrib['href']
				if href == element.text:
					if url_re.match(href):
						output.append(href)
					else:
						output.append('[['+href+']]')
				else:
					if element.text:
						output.append('[['+href+'|'+element.text+']]')
					else:
						output.append('[['+href+']]')

			elif element.tag in dumper_tags:
                dumper_tags = {
                    'emphasis': '//',
                    'strong':   '**',
                    'mark':     '__',
                    'strike':   '~~',
                    'code':     "''",
                    'tag':      '', # No additional annotation (apart from the visible @)
                }
				if element.text:
					tag = dumper_tags[element.tag]
					output.append(tag+element.text+tag)
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(element.tail)
