from app.engine.recipes import get_builtin
from app.engine.enrich import norm_url, analyse


GF = get_builtin("gloriafood")

SAMPLE_HTML = """
<html><head>
<title>Mario's Pizzeria</title>
<meta property="og:site_name" content="Mario's Pizzeria Official">
</head><body>
<a href="mailto:info@marios.com">Email us</a>
<a href="tel:+1-555-123-4567">Call</a>
Reach sales@marios.com or noreply@fbgcdn.com (skip this) and logo@cdn.png
<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>
<div data-glf-cuid="11111111-2222-3333-4444-555555555555"
     data-glf-ruid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"></div>
<a href="https://facebook.com/marios">fb</a>
<a href="https://instagram.com/marios">ig</a>
</body></html>
"""


def test_norm_url_adds_scheme_and_slash():
    assert norm_url("marios.com") == "https://marios.com/"
    assert norm_url("https://marios.com") == "https://marios.com/"


def test_analyse_confirms_platform_and_matched_fingerprint():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.on_platform is True
    assert lead.matched in GF.verify_fingerprints


def test_analyse_extracts_name():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.name == "Mario's Pizzeria"


def test_analyse_extracts_filtered_emails():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert "info@marios.com" in lead.emails
    assert "sales@marios.com" in lead.emails
    assert "noreply@fbgcdn.com" not in lead.emails
    assert "logo@cdn.png" not in lead.emails


def test_analyse_extracts_phone_from_tel():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert any("555" in p for p in lead.phones)


def test_analyse_extracts_recipe_ids():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert lead.ids["ruid"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert lead.ids["cuid"] == "11111111-2222-3333-4444-555555555555"


def test_analyse_extracts_socials():
    lead = analyse(GF, "https://marios.com/", SAMPLE_HTML)
    assert "facebook" in lead.socials
    assert "instagram" in lead.socials


def test_analyse_not_confirmed_when_absent():
    lead = analyse(GF, "https://x.com/", "<html><title>x</title></html>")
    assert lead.on_platform is False
    assert lead.matched == ""


def test_analyse_extractor_without_capture_group_is_safe():
    from app.engine.recipes import Recipe
    # extractor pattern with NO capture group must not raise
    rec = Recipe(id="c", category="Custom", type="C",
                 verify_fingerprints=["marios"],
                 id_extractors={"bad": r"data-glf-ruid"})
    lead = analyse(rec, "https://marios.com/", SAMPLE_HTML)
    assert lead.on_platform is True
    assert "bad" not in lead.ids   # gracefully skipped, no crash


def test_analyse_decodes_url_encoded_tel():
    from app.engine.recipes import get_builtin
    gf = get_builtin("gloriafood")
    html = ('<html><title>x</title><body>'
            '<a href="tel:0492%20432%20124">call</a>'
            '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
            '</body></html>')
    lead = analyse(gf, "https://x.com/", html)
    assert "0492 432 124" in lead.phones
    assert not any("%20" in p for p in lead.phones)


def test_analyse_filters_placeholder_emails():
    from app.engine.recipes import get_builtin
    gf = get_builtin("gloriafood")
    html = ('<html><title>x</title><body>'
            'contact user@domain.com or hi@mydomain.com or real@goodbiz.co.uk'
            '<script src="https://fbgcdn.com/embedder/js/ewm2.js"></script>'
            '</body></html>')
    lead = analyse(gf, "https://x.com/", html)
    assert "user@domain.com" not in lead.emails        # placeholder dropped
    assert "hi@mydomain.com" in lead.emails             # real domain NOT over-filtered
    assert "real@goodbiz.co.uk" in lead.emails
