# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import urllib
import urllib2
import json
import time
#import sys
import re
#import thread
import threading
import time
#import Queue
from urllib2 import HTTPError

import lazylibrarian
from lazylibrarian import logger, formatter, database #, SimpleCache
from lazylibrarian.gr import GoodReads

#import lib.fuzzywuzzy as fuzzywuzzy
from lib.fuzzywuzzy import fuzz #, process
from lib.unidecode import unidecode


class GoogleBooks:

    def __init__(self, name=None, type=None):
        self.name = name
        self.type = type
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
            'key': lazylibrarian.GB_API
        }

    def find_results(self, authorname=None, queue=None):
        threading.currentThread().name = "GB-SEARCH"
        resultlist = []
        # See if we should check ISBN field, otherwise ignore it
        try:
            isbn_check = int(authorname[:-1])
            if (len(str(isbn_check)) == 9) or (len(str(isbn_check)) == 12):
                api_strings = ['isbn:']
            else:
                api_strings = ['inauthor:', 'intitle:']
        except:
            api_strings = ['inauthor:', 'intitle:']

        api_hits = 0
        logger.debug('Now searching Google Books API with keyword: ' + self.name)

        for api_value in api_strings:
            startindex = 0
            if api_value == "isbn:":
                set_url = self.url + urllib.quote(api_value + self.name)
            else:
                set_url = self.url + urllib.quote(api_value + '"' + self.name + '"')

            try:
                startindex = 0
                resultcount = 0
                #removedResults = 0
                ignored = 0
                number_results = 1
                total_count = 0
                no_author_count = 0

                while startindex < number_results:

                    self.params['startIndex'] = startindex
                    URL = set_url + '&' + urllib.urlencode(self.params)

                    try:
                        jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
                        api_hits = api_hits + 1
                        number_results = jsonresults['totalItems']
                        logger.debug('Searching url: ' + URL)
                        if number_results == 0:
                            logger.warn('Found no results for %s with value: %s' % (api_value, self.name))
                            break
                        else:
                            pass
                    except HTTPError, err:
                        logger.warn('Google Books API Error [%s]: Check your API key or wait a while' % err.msg)
                        break

                    startindex = startindex + 40

                    for item in jsonresults['items']:

                        total_count = total_count + 1

                        # skip if no author, no author is no book.
                        try:
                            Author = item['volumeInfo']['authors'][0]
                        except KeyError:
                            logger.debug('Skipped a result without authorfield.')
                            no_author_count = no_author_count + 1
                            continue

                        valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])

                        if "All" not in valid_langs:  # don't care about languages, accept all
                            try:
                            # skip if language is not in valid list -
                                booklang = item['volumeInfo']['language']
                                if booklang not in valid_langs:
                                    logger.debug('Skipped a book with language %s' % booklang)
                                    ignored = ignored + 1
                                    continue
                            except KeyError:
                                ignored = ignored + 1
                                logger.debug('Skipped a result where no language is found')
                                continue

                        try:
                            bookpub = item['volumeInfo']['publisher']
                        except KeyError:
                            bookpub = None

                        try:
                            booksub = item['volumeInfo']['subtitle']
                        except KeyError:
                            booksub = None

                        try:
                            bookdate = item['volumeInfo']['publishedDate']
                        except KeyError:
                            bookdate = '0000-00-00'
                        bookdate = bookdate[:4]

                        try:
                            bookimg = item['volumeInfo']['imageLinks']['thumbnail']
                        except KeyError:
                            bookimg = 'images/nocover.png'

                        try:
                            bookrate = item['volumeInfo']['averageRating']
                        except KeyError:
                            bookrate = 0

                        try:
                            bookpages = item['volumeInfo']['pageCount']
                        except KeyError:
                            bookpages = '0'

                        try:
                            bookgenre = item['volumeInfo']['categories'][0]
                        except KeyError:
                            bookgenre = None

                        try:
                            bookdesc = item['volumeInfo']['description']
                        except KeyError:
                            bookdesc = 'Not available'

                        try:
                            num_reviews = item['volumeInfo']['ratingsCount']
                        except KeyError:
                            num_reviews = 0

                        try:
                            if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                                bookisbn = item['volumeInfo']['industryIdentifiers'][0]['identifier']
                            else:
                                bookisbn = 0
                        except KeyError:
                            bookisbn = 0

                        author_fuzz = fuzz.ratio(Author.lower(), authorname.lower())
                        book_fuzz = fuzz.ratio(item['volumeInfo']['title'].lower(), authorname.lower())
                        try:
                            isbn_check = int(authorname[:-1])
                            if (len(str(isbn_check)) == 9) or (len(str(isbn_check)) == 12):
                                isbn_fuzz = int(100)
                            else:
                                isbn_fuzz = int(0)
                        except:
                            isbn_fuzz = int(0)
                        highest_fuzz = max(author_fuzz, book_fuzz, isbn_fuzz)

#  Darkie67:
#        replacing German Umlauts and filtering out ":"
#
# PAB I think this is to avoid removing the book for bad characters?
# Do we need to remove books with bad characters in their name anyway?
# Use unidecode as a more thorough way to strip and see what still gets marked "bad"
#
#                        booknamealt = item['volumeInfo']['title']
#                        booknametmp1=booknamealt.replace(u'\xf6',u'oe')
#                        booknametmp2=booknametmp1.replace(u'\xe4',u'ae')
#                        booknametmp3=booknametmp2.replace(u'\xdf',u'ss')
#                        booknametmp4=booknametmp3.replace(u'\xc4',u'Ae')
#                        booknametmp5=booknametmp4.replace(u'\xdc',u'Ue')
#                        booknametmp6=booknametmp5.replace(u'\xd6',u'Oe')
#                        booknametmp7=booknametmp6.replace(':','')
#                        bookname=booknametmp7.replace(u'\xfc',u'ue')
                        bookname = item['volumeInfo']['title']
                        bookname = bookname.replace(':', '').replace('"', '').replace("'", "")
                        bookname = unidecode(u'%s' % bookname)
                        bookname = bookname.strip()  # strip whitespace
# Darkie67 end
                        resultlist.append({
                            'authorname': Author,
                            'bookid': item['id'],
                            'bookname': bookname,
                            'booksub': booksub,
                            'bookisbn': bookisbn,
                            'bookpub': bookpub,
                            'bookdate': bookdate,
                            'booklang': booklang,
                            'booklink': item['volumeInfo']['canonicalVolumeLink'],
                            'bookrate': float(bookrate),
                            'bookimg': bookimg,
                            'bookpages': bookpages,
                            'bookgenre': bookgenre,
                            'bookdesc': bookdesc,
                            'author_fuzz': author_fuzz,
                            'book_fuzz': book_fuzz,
                            'isbn_fuzz': isbn_fuzz,
                            'highest_fuzz': highest_fuzz,
                            'num_reviews': num_reviews
                        })

                        resultcount = resultcount + 1

            except KeyError:
                break

        logger.debug("Found %s total results" % total_count)
        logger.debug("Removed %s bad language results" % ignored)
        logger.debug("Removed %s books with no author" % no_author_count)
        logger.debug("Showing %s results for (%s) with keyword: %s" % (resultcount, api_value, authorname))
        logger.debug('The Google Books API was hit %s times for keyword %s' % (str(api_hits), self.name))
        queue.put(resultlist)

    def get_author_books(self, authorid=None, authorname=None, refresh=False):

        logger.debug('[%s] Now processing books with Google Books API' % authorname)
        # google doesnt like accents in author names
        aname = unidecode(u'%s' % authorname)

        set_url = self.url + urllib.quote('inauthor:' + '"' + aname + '"')
        URL = set_url + '&' + urllib.urlencode(self.params)

        books_dict = []
        api_hits = 0
        gr_lang_hits = 0
        lt_lang_hits = 0
        gb_lang_change = 0
        cache_hits = 0
        not_cached = 0

        # Artist is loading
        myDB = database.DBConnection()
        controlValueDict = {"AuthorID": authorid}
        newValueDict = {"Status": "Loading"}
        myDB.upsert("authors", newValueDict, controlValueDict)

        try:
            startindex = 0
            resultcount = 0
            removedResults = 0
            ignored = 0
            added_count = 0
            updated_count = 0
            book_ignore_count = 0
            total_count = 0
            number_results = 1

            valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])

            while startindex < number_results:

                self.params['startIndex'] = startindex
                URL = set_url + '&' + urllib.urlencode(self.params)

                try:
                    jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())
                    api_hits = api_hits + 1

                    number_results = jsonresults['totalItems']
                except HTTPError, err:
                    logger.warn('Google Books API Error [%s]: Check your API key or wait a while' % err.msg)
                    break

                if number_results == 0:
                    logger.warn('Found no results for %s' % (authorname))
                    break
                else:
                    logger.debug('Found %s results for %s' % (number_results, authorname))

                startindex = startindex + 40

                for item in jsonresults['items']:

                    total_count = total_count + 1

                    # skip if no author, no author is no book.
                    try:
                        Author = item['volumeInfo']['authors'][0]
                    except KeyError:
                        logger.debug('Skipped a result without authorfield.')
                        continue

                    try:
                        if item['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                            bookisbn = item['volumeInfo']['industryIdentifiers'][0]['identifier']
                        else:
                            bookisbn = ""
                    except KeyError:
                        bookisbn = ""

                    isbnhead = ""
                    if len(bookisbn) == 10:
                        isbnhead = bookisbn[0:3]

                    try:
                        booklang = item['volumeInfo']['language']
                    except KeyError:
                        booklang = "Unknown"

                    # do we care about language?
                    if "All" not in valid_langs:
                        if bookisbn != "":
                                # seems google lies to us, sometimes tells us books are in english when they are not
                            if booklang == "Unknown" or booklang == "en":
                                googlelang = booklang
                                match = myDB.action('SELECT lang FROM languages where isbn = "%s"' % (isbnhead)).fetchone()
                                if (match):
                                    booklang = match['lang']
                                    cache_hits = cache_hits + 1
                                    logger.debug("Found cached language [%s] for [%s]" % (booklang, isbnhead))

                                else:
                                    # no match in cache, try searching librarything for a language code using the isbn
                                    # if no language found, librarything return value is "invalid" or "unknown"
                                    # librarything returns plain text, not xml
                                    BOOK_URL = 'http://www.librarything.com/api/thingLang.php?isbn=' + bookisbn
                                    try:
                                        time.sleep(1)  # sleep 1 second to respect librarything api terms
                                        resp = urllib2.urlopen(BOOK_URL, timeout=30).read()
                                        lt_lang_hits = lt_lang_hits + 1
                                        logger.debug("LibraryThing reports language [%s] for %s" % (resp, isbnhead))

                                        if (resp != 'invalid' and resp != 'unknown'):
                                            booklang = resp  # found a language code
                                            myDB.action('insert into languages values ("%s", "%s")' % (isbnhead, booklang))
                                            logger.debug(u"LT language: " + booklang)
                                    except Exception, e:
                                        logger.error("Error finding results: ", e)

                                if googlelang == "en" and not booklang in "en-US, en-GB, eng":  # these are all english
                                    booknamealt = item['volumeInfo']['title']
                                    logger.debug("%s Google thinks [%s], we think [%s]" % (booknamealt, googlelang, booklang))
                                    gb_lang_change = gb_lang_change + 1
                            else:
                                match = myDB.action('SELECT lang FROM languages where isbn = "%s"' % (isbnhead)).fetchone()
                                if (not match):
                                    myDB.action('insert into languages values ("%s", "%s")' % (isbnhead, booklang))
                                    logger.debug(u"GB language: " + booklang)

                        # skip if language is in ignore list
                        if booklang not in valid_langs:
                            booknamealt = item['volumeInfo']['title']
                            logger.debug('Skipped [%s] with language %s' % (booknamealt, booklang))
                            ignored = ignored + 1
                            continue

                    try:
                        bookpub = item['volumeInfo']['publisher']
                    except KeyError:
                        bookpub = None
                    try:
                        booksub = item['volumeInfo']['subtitle']
                    except KeyError:
                        booksub = None

                    try:
                        bookdate = item['volumeInfo']['publishedDate']
                    except KeyError:
                        bookdate = '0000-00-00'

                    try:
                        bookimg = item['volumeInfo']['imageLinks']['thumbnail']
                    except KeyError:
                        bookimg = 'images/nocover.png'

                    try:
                        bookrate = item['volumeInfo']['averageRating']
                    except KeyError:
                        bookrate = 0

                    try:
                        bookpages = item['volumeInfo']['pageCount']
                    except KeyError:
                        bookpages = 0

                    try:
                        bookgenre = item['volumeInfo']['categories'][0]
                    except KeyError:
                        bookgenre = None

                    try:
                        bookdesc = item['volumeInfo']['description']
                    except KeyError:
                        bookdesc = None

                    bookid = item['id']
#  Darkie67:
# replacing German Umlauts and filtering out ":"  ## PAB no idea why we filter out ':' ??
#
#                    booknamealt = item['volumeInfo']['title']
#                    booknametmp1=booknamealt.replace(u'\xf6',u'oe')
#                    booknametmp2=booknametmp1.replace(u'\xe4',u'ae')
#                    booknametmp3=booknametmp2.replace(u'\xdf',u'ss')
#                    booknametmp4=booknametmp3.replace(u'\xc4',u'Ae')
#                    booknametmp5=booknametmp4.replace(u'\xdc',u'Ue')
#                    booknametmp6=booknametmp5.replace(u'\xd6',u'Oe')
#                    booknametmp7=booknametmp6.replace(':','')
#                    bookname=booknametmp7.replace(u'\xfc',u'ue')
                    bookname = item['volumeInfo']['title']
                    bookname = bookname.replace(':', '').replace('"', '').replace("'", "")
                    bookname = unidecode(u'%s' % bookname)
                    bookname = bookname.strip()  # strip whitespace
# Darkie67 end
                    booklink = item['volumeInfo']['canonicalVolumeLink']
                    bookrate = float(bookrate)

                    find_book_status = myDB.select('SELECT * FROM books WHERE BookID = "%s"' % bookid)
                    if find_book_status:
                        for resulted in find_book_status:
                            book_status = resulted['Status']
                    else:
                        book_status = lazylibrarian.NEWBOOK_STATUS

                    if not (re.match('[^\w-]', bookname)):  # remove books with bad characters in title
                        if book_status != "Ignored":
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {
                                "AuthorName":   authorname,
                                "AuthorID":     authorid,
                                "AuthorLink":   "",
                                "BookName":     bookname,
                                "BookSub":      booksub,
                                "BookDesc":     bookdesc,
                                "BookIsbn":     bookisbn,
                                "BookPub":      bookpub,
                                "BookGenre":    bookgenre,
                                "BookImg":      bookimg,
                                "BookLink":     booklink,
                                "BookRate":     bookrate,
                                "BookPages":    bookpages,
                                "BookDate":     bookdate,
                                "BookLang":     booklang,
                                "Status":       book_status,
                                "BookAdded":    formatter.today(),
                                "Series":       None,
                                "SeriesOrder":  None
                            }
                            resultcount = resultcount + 1

                            myDB.upsert("books", newValueDict, controlValueDict)
                            logger.debug(u"book found " + bookname + " " + bookdate)
                            if not find_book_status:
                                logger.debug("[%s] Added book: %s [%s]" % (authorname, bookname, booklang))
                                added_count = added_count + 1
                            else:
                                updated_count = updated_count + 1
                                logger.debug("[%s] Updated book: %s" % (authorname, bookname))
                        else:
                            book_ignore_count = book_ignore_count + 1
                    else:
                        logger.debug("[%s] removed book for bad characters" % (bookname))
                        removedResults = removedResults + 1

        except KeyError:
            pass

        logger.debug('[%s] The Google Books API was hit %s times to populate book list' % (authorname, str(api_hits)))

        unignoredbooks = myDB.select('SELECT COUNT(BookName) as unignored FROM books WHERE AuthorID="%s" AND Status != "Ignored"' % authorid)
        bookCount = myDB.select('SELECT COUNT(BookName) as counter FROM books WHERE AuthorID="%s"' % authorid)
        lastbook = myDB.action('SELECT BookName, BookLink, BookDate from books WHERE AuthorID="%s" AND Status != "Ignored" order by BookDate DESC' % authorid).fetchone()

        if lastbook:  # maybe there are no books [remaining] for this author
            lastbookname = lastbook['BookName']
            lastbooklink = lastbook['BookLink']
            lastbookdate = lastbook['BookDate']
        else:
            lastbookname = None
            lastbooklink = None
            lastbookdate = None

        controlValueDict = {"AuthorID": authorid}
        newValueDict = {
            "Status": "Active",
                "TotalBooks": bookCount[0]['counter'],
                "UnignoredBooks": unignoredbooks[0]['unignored'],
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate
        }

        myDB.upsert("authors", newValueDict, controlValueDict)

        logger.debug("Found %s total books for author" % total_count)
        logger.debug("Removed %s bad language results for author" % ignored)
        logger.debug("Removed %s bad character results for author" % removedResults)
        logger.debug("Ignored %s books by author marked as Ignored" % book_ignore_count)
        logger.debug("Imported/Updated %s books for author" % resultcount)

        myDB.action('insert into stats values ("%s", %i, %i, %i, %i, %i, %i, %i, %i)' % (authorname, api_hits, gr_lang_hits, lt_lang_hits, gb_lang_change, cache_hits, ignored, removedResults, not_cached))

        if refresh:
            logger.info("[%s] Book processing complete: Added %s books / Updated %s books" % (authorname, str(added_count), str(updated_count)))
        else:
            logger.info("[%s] Book processing complete: Added %s books to the database" % (authorname, str(added_count)))

        return books_dict

    def find_book(self, bookid=None, queue=None):
        threading.currentThread().name = "GB-ADD-BOOK"
        myDB = database.DBConnection()

        URL = 'https://www.googleapis.com/books/v1/volumes/' + str(bookid) + "?key=" + lazylibrarian.GB_API
        jsonresults = json.JSONDecoder().decode(urllib2.urlopen(URL, timeout=30).read())

#  Darkie67:
#        replacing German Umlauts and filtering out ":"
#
#        booknamealt = jsonresults['volumeInfo']['title']
#        booknametmp1=booknamealt.replace(u'\xf6',u'oe')
#        booknametmp2=booknametmp1.replace(u'\xe4',u'ae')
#        booknametmp3=booknametmp2.replace(u'\xdf',u'ss')
#        booknametmp4=booknametmp3.replace(u'\xc4',u'Ae')
#        booknametmp5=booknametmp4.replace(u'\xdc',u'Ue')
#        booknametmp6=booknametmp5.replace(u'\xd6',u'Oe')
#        booknametmp7=booknametmp6.replace(':','')
#        bookname=booknametmp7.replace(u'\xfc',u'ue')
        bookname = jsonresults['volumeInfo']['title']
        bookname = bookname.replace(':', '').replace('"', '').replace("'", "")
        bookname = unidecode(u'%s' % bookname)
        bookname = bookname.strip()  # strip whitespace
# Darkie67 end
        try:
            authorname = jsonresults['volumeInfo']['authors'][0]
        except KeyError:
            logger.debug('Book %s does not contain author field' % bookname)

        try:
            # warn if language is in ignore list, but user said they wanted this book
            booklang = jsonresults['volumeInfo']['language']
            valid_langs = ([valid_lang.strip() for valid_lang in lazylibrarian.IMP_PREFLANG.split(',')])
            if booklang not in valid_langs:
                logger.debug('Book %s language does not match preference' % bookname)
        except KeyError:
            logger.debug('Book does not have language field')
            booklang = "Unknown"

        try:
            bookpub = jsonresults['volumeInfo']['publisher']
        except KeyError:
            bookpub = None

        try:
            booksub = jsonresults['volumeInfo']['subtitle']
        except KeyError:
            booksub = None

        try:
            bookdate = jsonresults['volumeInfo']['publishedDate']
        except KeyError:
            bookdate = '0000-00-00'

        try:
            bookimg = jsonresults['volumeInfo']['imageLinks']['thumbnail']
        except KeyError:
            bookimg = 'images/nocover.png'

        try:
            bookrate = jsonresults['volumeInfo']['averageRating']
        except KeyError:
            bookrate = 0

        try:
            bookpages = jsonresults['volumeInfo']['pageCount']
        except KeyError:
            bookpages = 0

        try:
            bookgenre = jsonresults['volumeInfo']['categories'][0]
        except KeyError:
            bookgenre = None

        try:
            bookdesc = jsonresults['volumeInfo']['description']
        except KeyError:
            bookdesc = None

        try:
            if jsonresults['volumeInfo']['industryIdentifiers'][0]['type'] == 'ISBN_10':
                bookisbn = jsonresults['volumeInfo']['industryIdentifiers'][0]['identifier']
            else:
                bookisbn = None
        except KeyError:
            bookisbn = None

        booklink = jsonresults['volumeInfo']['canonicalVolumeLink']
        bookrate = float(bookrate)

        name = jsonresults['volumeInfo']['authors'][0]
        GR = GoodReads(name)
        author = GR.find_author_id()
        if author:
            AuthorID = author['authorid']

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "AuthorName":   authorname,
            "AuthorID":     AuthorID,
            "AuthorLink":   "",
            "BookName":     bookname,
            "BookSub":      booksub,
            "BookDesc":     bookdesc,
            "BookIsbn":     bookisbn,
            "BookPub":      bookpub,
            "BookGenre":    bookgenre,
            "BookImg":      bookimg,
            "BookLink":     booklink,
            "BookRate":     bookrate,
            "BookPages":    bookpages,
            "BookDate":     bookdate,
            "BookLang":     booklang,
            "Status":       "Wanted",
            "BookAdded":    formatter.today()
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.debug("%s added to the books database" % bookname)
