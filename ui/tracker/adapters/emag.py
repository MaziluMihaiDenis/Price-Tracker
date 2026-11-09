from tracker.adapters.base import SiteAdapter, json_ld_nodes, read_detail

MAX_SPECS = 60


class EmagAdapter(SiteAdapter):
    """eMAG product pages: a JSON-LD Product block with an Offer (price in RON)."""

    name = "eMAG"
    domains = ("emag.ro",)
    default_currency = "RON"
    default_period = "one_time"

    def _details(self, soup):
        """The brand (structured data) and the specifications table (milestone 3c)."""
        details = {}
        read_detail(details, "brand", lambda: self._brand(soup))
        read_detail(details, "specs", lambda: self._specs(soup))
        return details

    @staticmethod
    def _brand(soup):
        for node in json_ld_nodes(soup):
            if "offers" in node and node.get("brand"):
                brand = node["brand"]
                name = brand.get("name") if isinstance(brand, dict) else brand
                return str(name).strip()[:200] if name else None
        return None

    @staticmethod
    def _specs(soup):
        """{"Tip produs": "Gel de curatare", "Tipul de ten": "Uscat, Normal", ...}"""
        specs = {}
        for row in soup.select(".specifications-body tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) != 2:
                continue
            label = " ".join(cells[0].get_text(" ").split())[:60]
            lines = [" ".join(line.split()) for line in cells[1].get_text("\n").splitlines()]
            value = ", ".join(line for line in lines if line)[:200]
            if label and value and label not in specs:
                specs[label] = value
            if len(specs) >= MAX_SPECS:
                break
        return specs
