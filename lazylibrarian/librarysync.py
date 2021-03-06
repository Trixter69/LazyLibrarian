import os
import re
import lazylibrarian
from lazylibrarian import logger, database, importer, formatter, common
from lazylibrarian.gr import GoodReads
from lib.fuzzywuzzy import fuzz
from xml.etree import ElementTree
import lib.zipfile as zipfile
from lib.mobi import Mobi


def opf_file(search_dir=None):
    # find an .opf file in this directory
    # return full pathname of file, or empty string if no opf found
    if search_dir and os.path.isdir(search_dir):
        for fname in os.listdir(search_dir):
            if fname.endswith('.opf'):
                return os.path.join(search_dir, fname).encode(lazylibrarian.SYS_ENCODING)
    return ""                           


def get_book_info(fname):
    # only handles epub, mobi and opf for now,
    # for pdf see below
    res = {}
    if not '.' in fname:
        return res
    words = fname.split('.')
    extn = words[len(words) - 1]

    if extn == "mobi":
        try:
            book = Mobi(fname)
            book.parse()
        except:
            return res
        res['creator'] = book.author()
        res['title'] = book.title()
        res['language'] = book.language()
        res['identifier'] = book.isbn()
        return res

    # none of the pdfs in my library had language,isbn
    # most didn't have author, or had the wrong author
    # (author set to publisher, or software used)
    # so probably not much point in looking at pdfs
    #
    # if (extn == "pdf"):
    #	  pdf = PdfFileReader(open(fname, "rb"))
    #	  txt = pdf.getDocumentInfo()
          # repackage the data here to get components we need
    #     res = {}
    #     for s in ['title','language','creator']:
    #         res[s] = txt[s]
    #	  res['identifier'] = txt['isbn']
    #	  return res

    if extn == "epub":
        # prepare to read from the .epub file
        zipdata = zipfile.ZipFile(fname)
        # find the contents metafile
        txt = zipdata.read('META-INF/container.xml')
        tree = ElementTree.fromstring(txt)
        n = 0
        cfname = ""
        if not len(tree):
            return res
        while n < len(tree[0]):
            att = str(tree[0][n].attrib)
            if 'full-path' in att:
                cfname = ("%s" % att)  # extract metadata filename
                cfname = cfname.split(',')[1].split(':')[1].strip('\' }')
            n = n + 1

        # grab the metadata block from the contents metafile
        txt = zipdata.read(cfname)
        tree = ElementTree.fromstring(txt)
    else:
        if extn == "opf":
            txt = open(fname).read()
            tree = ElementTree.fromstring(txt)
        else:
            return ""

    # repackage the data
    if not len(tree):
        return res
    n = 0
    while n < len(tree[0]):
        tag = str(tree[0][n].tag).split('}')[1]
        txt = tree[0][n].text
        attrib = str(tree[0][n].attrib)
        isbn = ""
        if 'title' in tag.lower():
            res['title'] = txt
        elif 'language' in tag.lower():
            res['language'] = txt
        elif 'creator' in tag.lower():
            res['creator'] = txt
        elif 'identifier' in tag.lower() and 'isbn' in attrib.lower():
            if formatter.is_valid_isbn(txt):
                res['identifier'] = isbn
        n = n + 1
    return res


def find_book_in_db(myDB, author, book):
# PAB fuzzy search for book in library, return LL bookid if found or zero
# if not, return bookid to more easily update status
    # prefer an exact match on author & book
    match = myDB.action(
        'SELECT BookID FROM books where AuthorName="%s" and BookName="%s"' %
        (author, book)).fetchone()
    if match:
        logger.debug('Exact match [%s]' % book)
        return match['BookID']
    else:
        # No exact match
        # Try a more complex fuzzy match against each book in the db by this author
        # Using hard-coded ratios for now, ratio high (>90), partial_ratio lower (>65)
        # These are results that work well on my library, minimal false matches and no misses on books that should be matched
        # Maybe make ratios configurable in config.ini later
#
        books = myDB.select(
            'SELECT BookID,BookName FROM books where AuthorName="%s"' %
            author)
        best_ratio = 0
        best_partial = 0
        ratio_name = ""
        partial_name = ""
        ratio_id = 0
        partial_id = 0
        logger.debug("Found %s books for %s" % (len(books), author))
        for a_book in books:
            # tidy up everything to raise fuzziness scores
            book_lower = common.remove_accents(book.lower())
            a_book_lower = common.remove_accents(a_book['BookName'].lower())
            #
            ratio = fuzz.ratio(book_lower, a_book_lower)
            partial = fuzz.partial_ratio(book_lower, a_book_lower)
            if ratio > best_ratio:
                best_ratio = ratio
                ratio_name = a_book['BookName']
                ratio_id = a_book['BookID']
            if partial > best_partial:
                best_partial = partial
                partial_name = a_book['BookName']
                partial_id = a_book['BookID']

            else:
                if partial == best_partial:
                    # prefer the match closest to the left, ie prefer starting with a match and ignoring the rest
                    # this eliminates most false matches against omnibuses
                    if a_book_lower.find(book_lower) < partial_name.lower().find(book_lower):
                        logger.debug(
                            "Fuzz left prefer [%s] over [%s]" %
                            (a_book['BookName'], partial_name))
                        best_partial = partial
                        partial_name = a_book['BookName']
                        partial_id = a_book['BookID']
            #
        if best_ratio > 90:
            logger.debug(
                "Fuzz match   ratio [%d] [%s] [%s]" %
                (best_ratio, book, ratio_name))
            return ratio_id
        if best_partial > 65:
            logger.debug(
                "Fuzz match partial [%d] [%s] [%s]" %
                (best_partial, book, partial_name))
            return partial_id

        logger.debug(
            'Fuzz failed [%s - %s] ratio [%d,%s], partial [%d,%s]' %
            (author, book, best_ratio, ratio_name, best_partial, partial_name))
        return 0


def LibraryScan(dir=None):
    if not dir:
        if not lazylibrarian.DOWNLOAD_DIR:
            return
        else:
            dir = lazylibrarian.DOWNLOAD_DIR

    if not os.path.isdir(dir):
        logger.warn(
            'Cannot find directory: %s. Not scanning' %
            dir.decode(lazylibrarian.SYS_ENCODING, 'replace'))
        return

    myDB = database.DBConnection()

    myDB.action('drop table if exists stats')
    myDB.action(
        'create table stats ( authorname text, GR_book_hits int, GR_lang_hits int, LT_lang_hits int, GB_lang_change, cache_hits int, bad_lang int, bad_char int, uncached int )')

    new_authors = []

    logger.info(
        'Scanning ebook directory: %s' %
        dir.decode(lazylibrarian.SYS_ENCODING, 'replace'))

    new_book_count = 0
    file_count = 0

    if lazylibrarian.FULL_SCAN:
        books = myDB.select(
            'select AuthorName, BookName, BookFile, BookID from books where Status="Open"')
        status = lazylibrarian.NOTFOUND_STATUS
        logger.info('Missing books will be marked as %s' % status)
        for book in books:
            bookName = book['BookName']
            bookAuthor = book['AuthorName']
            bookID = book['BookID']
            bookfile = book['BookFile']

            if not(bookfile and os.path.isfile(bookfile)):
                myDB.action(
                    'update books set Status="%s" where BookID="%s"' %
                    (status, bookID))
                myDB.action(
                    'update books set BookFile="" where BookID="%s"' %
                    bookID)
                logger.warn(
                    'Book %s - %s updated as not found on disk' %
                    (bookAuthor, bookName))
            # for book_type in getList(lazylibrarian.EBOOK_TYPE):
            #	bookName = book['BookName']
            #	bookAuthor = book['AuthorName']
            # Default destination path, should be allowed change per config file.
            #	dest_path = lazylibrarian.EBOOK_DEST_FOLDER.replace('$Author', bookAuthor).replace('$Title', bookName)
            # dest_path = authorname+'/'+bookname
            #	global_name = lazylibrarian.EBOOK_DEST_FILE.replace('$Author', bookAuthor).replace('$Title', bookName)
#
            #	encoded_book_path = os.path.join(dir,dest_path,global_name + "." + book_type).encode(lazylibrarian.SYS_ENCODING)
            #	if os.path.isfile(encoded_book_path):
            #		book_exists = True
            # if not book_exists:
            #	myDB.action('update books set Status=? where AuthorName=? and BookName=?',[status,bookAuthor,bookName])
            # logger.info('Book %s updated as not found on disk' %
            # encoded_book_path.decode(lazylibrarian.SYS_ENCODING, 'replace') )
                if bookAuthor not in new_authors:
                    new_authors.append(bookAuthor)

    # guess this was meant to save repeat-scans of the same directory
    # if it contains multiple formats of the same book, but there was no code
    # that looked at the array. renamed from latest to processed to make
    # purpose clearer
    processed_subdirectories = []

    matchString = ''
    for char in lazylibrarian.EBOOK_DEST_FILE:
        matchString = matchString + '\\' + char
    # massage the EBOOK_DEST_FILE config parameter into something we can use
    # with regular expression matching
    booktypes = ''
    count = -1
    booktype_list = formatter.getList(lazylibrarian.EBOOK_TYPE)
    for book_type in booktype_list:
        count += 1
        if count == 0:
            booktypes = book_type
        else:
            booktypes = booktypes + '|' + book_type
    matchString = matchString.replace("\\$\\A\\u\\t\\h\\o\\r", "(?P<author>.*?)").replace(
        "\\$\\T\\i\\t\\l\\e", "(?P<book>.*?)") + '\.[' + booktypes + ']'
    pattern = re.compile(matchString, re.VERBOSE)

    for r, d, f in os.walk(dir):
        for directory in d[:]:
            if directory.startswith("."):
                d.remove(directory)
            # prevent magazine being scanned
            if directory.startswith("_"):
                d.remove(directory)
        for files in f:
            file_count += 1
            subdirectory = r.replace(dir, '')
            # Added new code to skip if we've done this directory before. Made this conditional with a switch in config.ini
            # in case user keeps multiple different books in the same
            # subdirectory
            if (lazylibrarian.IMP_SINGLEBOOK) and (subdirectory in processed_subdirectories):
                logger.debug("[%s] already scanned" % subdirectory)
            else:
# 			If this is a book, try to get author/title/isbn/language
# 			If metadata.opf exists, use that
# 			else if epub or mobi, read metadata from the book
# 			else have to try pattern match for author/title	and look up isbn/lang from LT or GR late
                match = 0
                extn = ""
                
                if '.' in files:
                    words = files.split('.')
                    extn = words[len(words) - 1]
                    
                if formatter.is_valid_booktype(files):
                    logger.debug(
                        "[%s] Now scanning subdirectory %s" %
                        (dir.decode(lazylibrarian.SYS_ENCODING, 'replace'), subdirectory.decode(lazylibrarian.SYS_ENCODING, 'replace')))
                    
                    # calibre uses "metadata.opf", LL uses "bookname - authorname.opf"
                    # just look for any .opf file in the current directory since we don't know 
                    # LL preferred authorname/bookname at this point
                    metafile = opf_file(r)
                    try:
                        res = get_book_info(metafile)
                    except:
                        res = {}
                    if 'title' in res and 'creator' in res:  # this is the minimum we need
                        book = res['title']
                        author = res['creator']
                        if 'language' in res:
                            language = res['language']
                        else:
                            language = ""
                        if 'identifier' in res:
                            isbn = res['identifier']
                        else:
                            isbn = ""
                        match = 1
                        logger.debug(
                            "file meta [%s] [%s] [%s] [%s]" %
                            (isbn, language, author, book))
                    else:
                        logger.debug("File meta incomplete in %s" % metafile)

                    if not match:
                        # it's a book, but no external metadata found
                        # if it's an epub or a mobi we can try to read metadata
                        # from it
                        if (extn == "epub") or (extn == "mobi"):
                            book_filename = os.path.join(r, files).encode(lazylibrarian.SYS_ENCODING)
                            try:
                                res = get_book_info(book_filename)
                            except:
                                res = {}
                            if 'title' in res and 'creator' in res:  # this is the minimum we need
                                book = res['title']
                                author = res['creator']
                                if 'language' in res:
                                    language = res['language']
                                else:
                                    language = ""
                                if 'identifier' in res:
                                    isbn = res['identifier']
                                else:
                                    isbn = ""
                                logger.debug("book meta [%s] [%s] [%s] [%s]" %
                                    (isbn, language, author, book))
                                match = 1
                            else:
                                logger.debug("Book meta incomplete in %s" % book_filename)

                if not match:
                    match = pattern.match(files)
                    if match:
                        author = match.group("author")
                        book = match.group("book")
                    else:
                        logger.debug("Pattern match failed [%s]" % files)

                if match:
                    processed_subdirectories.append(
                        subdirectory)  # flag that we found a book in this subdirectory
                    #
                    # If we have a valid looking isbn, and language != "Unknown", add it to cache
                    #
                    if not language:
                        language = "Unknown"

                    if not formatter.is_valid_isbn(isbn):
                        isbn = ""
                    if isbn != "" and language != "Unknown":
                        logger.debug(
                            "Found Language [%s] ISBN [%s]" %
                            (language, isbn))
                        # we need to add it to language cache if not already
                        # there, is_valid_isbn has checked length is 10 or 13
                        if len(isbn) == 10:
                            isbnhead = isbn[0:3]
                        else:
                            isbnhead = isbn[3:6]
                        match = myDB.action(
                            'SELECT lang FROM languages where isbn = "%s"' %
                            (isbnhead)).fetchone()
                        if not match:
                            myDB.action(
                                'insert into languages values ("%s", "%s")' %
                                (isbnhead, language))
                            logger.debug(
                                "Cached Lang [%s] ISBN [%s]" %
                                (language, isbnhead))
                        else:
                            logger.debug(
                                "Already cached Lang [%s] ISBN [%s]" %
                                (language, isbnhead))

                    # get authors name in a consistent format
                    if "," in author:  # "surname, forename"
                        words = author.split(',')
                        author = words[1].strip() + ' ' + words[0].strip()  # "forename surname"
                    if author[1] == ' ':        
                        author = author.replace(' ', '.')
                        author = author.replace('..', '.')

                    # Check if the author exists, and import the author if not,
                    # before starting any complicated book-name matching to save repeating the search
                    #
                    check_exist_author = myDB.action(
                        'SELECT * FROM authors where AuthorName="%s"' %
                        author).fetchone()
                    if not check_exist_author and lazylibrarian.ADD_AUTHOR:
                        # no match for supplied author, but we're allowed to
                        # add new ones

                        GR = GoodReads(author)
                        try:
                            author_gr = GR.find_author_id()
                        except:
                            logger.warn(
                                "Error finding author id for [%s]" %
                                author)
                            continue

                        # only try to add if GR data matches found author data
                        # not sure what this is for, never seems to fail??
                        if author_gr:
                            authorname = author_gr['authorname']

                            # "J.R.R. Tolkien" is the same person as "J. R. R. Tolkien" and "J R R Tolkien"
                            match_auth = author.replace('.', '_')
                            match_auth = match_auth.replace(' ', '_')
                            match_auth = match_auth.replace('__', '_')
                            match_name = authorname.replace('.', '_')
                            match_name = match_name.replace(' ', '_')
                            match_name = match_name.replace('__', '_')
                            match_name = common.remove_accents(match_name)
                            match_auth = common.remove_accents(match_auth)
                            # allow a degree of fuzziness to cater for different accented character handling.
                            # some author names have accents,
                            # filename may have the accented or un-accented version of the character
                            # The currently non-configurable value of fuzziness might need to go in config
                            # We stored GoodReads unmodified author name in
                            # author_gr, so store in LL db under that
                            match_fuzz = fuzz.ratio(match_auth, match_name)
                            if match_fuzz < 90:
                                logger.debug(
                                    "Failed to match author [%s] fuzz [%d]" %
                                    (author, match_fuzz))
                                logger.debug(
                                    "Failed to match author [%s] to authorname [%s]" %
                                    (match_auth, match_name))

                            # To save loading hundreds of books by unknown
                            # authors at GR or GB, ignore if author "Unknown"
                            if (author != "Unknown") and (match_fuzz >= 90):
                                # use "intact" name for author that we stored in
                                # GR author_dict, not one of the various mangled versions
                                # otherwise the books appear to be by a
                                # different author!
                                author = author_gr['authorname']
                                # this new authorname may already be in the
                                # database, so check again
                                check_exist_author = myDB.action(
                                    'SELECT * FROM authors where AuthorName="%s"' %
                                    author).fetchone()
                                if not check_exist_author:
                                    logger.debug(
                                        "Adding new author [%s]" %
                                        author)
                                    if author not in new_authors:
                                        new_authors.append(author)
                                    try:
                                        importer.addAuthorToDB(author)
                                        check_exist_author = myDB.action(
                                            'SELECT * FROM authors where AuthorName="%s"' %
                                            author).fetchone()
                                    except:
                                        continue

                    # check author exists in db, either newly loaded or already
                    # there
                    if not check_exist_author:
                        logger.debug(
                            "Failed to match author [%s] in database" %
                            author)
                    else:
                        # author exists, check if this book by this author is in our database
                        # metadata might have quotes in book name
                        book = book.replace('"', '').replace("'", "")
                        bookid = find_book_in_db(myDB, author, book)
                        if bookid:
                            # check if book is already marked as "Open" (if so,
                            # we already had it)
                            check_status = myDB.action(
                                'SELECT Status from books where BookID="%s"' %
                                bookid).fetchone()
                            if check_status['Status'] != 'Open':
                                # update status as we've got this book
                                myDB.action(
                                    'UPDATE books set Status="Open" where BookID="%s"' %
                                    bookid)
                                book_filename = os.path.join(
                                    r,
                                    files).encode(
                                        lazylibrarian.SYS_ENCODING)
                                # update book location so we can check if it
                                # gets removed, or allow click-to-open
                                myDB.action(
                                    'UPDATE books set BookFile="%s" where BookID="%s"' %
                                    (book_filename, bookid))
                                new_book_count += 1

    cachesize = myDB.action("select count(*) from languages").fetchone()
    logger.info(
        "%s new/modified books found and added to the database" %
        new_book_count)
    logger.info("%s files processed" % file_count)
    if new_book_count:
        stats = myDB.action(
            "SELECT sum(GR_book_hits), sum(GR_lang_hits), sum(LT_lang_hits), sum(GB_lang_change), sum(cache_hits), sum(bad_lang), sum(bad_char), sum(uncached) FROM stats").fetchone()
        if lazylibrarian.BOOK_API == "GoogleBooks":
            logger.debug(
                "GoogleBooks was hit %s times for books" %
                stats['sum(GR_book_hits)'])
            logger.debug(
                "GoogleBooks language was changed %s times" %
                stats['sum(GB_lang_change)'])
        if lazylibrarian.BOOK_API == "GoodReads":
            logger.debug(
                "GoodReads was hit %s times for books" %
                stats['sum(GR_book_hits)'])
            logger.debug(
                "GoodReads was hit %s times for languages" %
                stats['sum(GR_lang_hits)'])
        logger.debug(
            "LibraryThing was hit %s times for languages" %
            stats['sum(LT_lang_hits)'])
        logger.debug(
            "Language cache was hit %s times" %
            stats['sum(cache_hits)'])
        logger.debug(
            "Unwanted language removed %s books" %
            stats['sum(bad_lang)'])
        logger.debug(
            "Unwanted characters removed %s books" %
            stats['sum(bad_char)'])
        logger.debug(
            "Unable to cache %s books with missing ISBN" %
            stats['sum(uncached)'])
    logger.debug("ISBN Language cache holds %s entries" % cachesize['count(*)'])
    stats = len(
        myDB.select('select BookID from Books where status="Open" and BookLang="Unknown"'))
    if stats:
        logger.warn(
            "There are %s books in your library with unknown language" %
            stats)

    logger.debug('Updating %i authors' % len(new_authors))
    for auth in new_authors:
        havebooks = len(
            myDB.select('select BookName from Books where status="%s" and AuthorName="%s"' %
                        ('Open', auth)))
        myDB.action(
            'UPDATE authors set HaveBooks="%s" where AuthorName="%s"' %
            (havebooks, auth))
        totalbooks = len(
            myDB.select('select BookName from Books where status!="%s" and AuthorName="%s"' %
                        ('Ignored', auth)))
        myDB.action(
            'UPDATE authors set UnignoredBooks="%s" where AuthorName="%s"' %
            (totalbooks, auth))

    logger.info('Library scan complete')
